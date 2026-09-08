# Anki Garden 2.2.0 functional release audit

The audit fixed a learner-visible false streak and defects in the release QA
itself. Existing progression and economy rules are preserved. Public release
remains on hold for the separately documented pacing requirement.

## Candidate and preservation

The baseline was the dirty working tree at `332c978ec4d5a10e2ac859f7a8611026c9ad5270`.
Its source, tests, documentation, scripts, patch, and previous archive were saved
under [the audit directory](../build/functional-release-audit-20260907/).
Concurrent capture, reviewer-display, dashboard, and simulator edits were retained.
The reviewer files passed 123 relevant existing Anki Qt checks; the final popup
adjustment received a native smoke check. Concurrent work is not attributed to
this audit. `audit-changes.patch` records the combined changes in audited paths
relative to the dirty baseline, including concurrent simulator work.

All native work used fresh, uniquely named disposable Anki 26.08.1 profiles,
with automatic/media sync disabled and no credentials. Process, window, profile,
instance key, collection path, and installed payload identities were checked.
The normal profile/add-on installation was not modified.

## Findings and fixes

| Finding | Impact and resolution | Evidence |
|---|---|---|
| Fresh gardens displayed a one-day streak with zero reviews | Default `last_active_day` was mistaken for a proven study day. The shared presentation now requires a positive saved streak or a completed card. Saved progress and reward calculations are unchanged. | Native fresh-install Activity screenshot; existing streak test extended with the actual zero-streak/default-date case. |
| Simulator used a newly earned streak Charge before it was earned | The modeled day-30 total exceeded production by 100 Growth for the moderate collection-first strategy. Move pre-study supply use before streak-item grants, matching the production replay strategy. | Original mismatch retained; the affected 365-day scenario passes. |
| Daily Shared Growth rounding differed from per-card production | The power landmark/mastery case overcounted 10 Growth on day 266. Concurrent simulator work now selects per-answer replay for fractional Shared lanes and routing crossings. The affected full-year case passes. | Raw mismatch and corrected production replay retained. |
| Zero-value Autumn source broke exact trace comparisons | Record an Autumn source only when a bonus is actually credited. This changes reporting, not earned Coins. | Rating trace and yearly parity checks. |
| Durable parity fixtures still expected retired completion mechanics | Replace five-completion-cycle and Snowy Charge/counter expectations with current daily completion and immediate Snowy Growth behavior. | Focused real-SQLite durability and state comparisons pass. |
| Artwork evidence rejected visually identical encodings | Verify exact alpha and every visible RGBA pixel, permit irrelevant RGB differences only where alpha is zero, and refresh ten calibration hashes after that proof. Geometry and image assets are unchanged. | 756 artwork checks passed. |
| Stale fixtures and QA documentation | Update removed fields, display copy, report/catalog expectations, home-state fixtures, current capture-count diagnostics, and obsolete ledger-schema assertions using the production schema constant. Replace outdated release journeys and correct contradictory mechanics in the presentation contract. | Focused existing checks and the release-evidence lane. |

No new test files were added. The fresh-streak regression extends an existing
shared behavior test; the full existing parity test protects the simulator fix.

## Functional evidence

- **Baseline:** 30 default-lane failures; 21 release-evidence failures.
- **Release-evidence lane:** 800 passed, 37 skipped. The default Python environment
  lacks Anki Qt; its skips are not counted as native passes.
- **Anki Qt checks:** 53 existing interaction, settings-overflow, and dialog tests
  passed using Anki's bundled libraries.
- **Streak fix:** 114 affected existing presentation/Home/Progress checks passed.
  The final shared-state and simulator subset passed 68 checks (one full-matrix
  test runs separately).
- **Native startup/onboarding:** Actual installer package folder, artwork preview,
  mouse selection, keyboard placement, Nurture, automatic completion, one welcome
  grant, and four real answer ratings passed.
- **Native transactions:** Species, Fertilizer, Growth Charge, decoration/scenery,
  duplicate request, insufficient balance, failed-save rollback/retry, placement,
  swap/undo, and use of a Charge passed.
- **Native study:** Four real answers produced four eligible events and 10 base
  Growth each. Undo/re-answer kept earned Coins and Growth unchanged.
- **Native restart:** Plants, wallet, inventory, equipment, effect state, purchase
  identities, settings, review totals, and completed onboarding persisted.
- **Native migration:** A separate schema-27 fixture migrated to schema 30 with
  its exact recovery backup, 543 Coins, 750 plant Growth, plant identity, ownership,
  and correct equipped effects preserved.
- **Native usability:** Main panels, keyboard Settings dismissal, both Anki themes,
  and 16 narrow/normal navigation states passed. The requested 800px width clamps
  to the supported 860px minimum; it is not an 800px-wide acceptance claim.
- **Installer preservation:** Anki's actual installer accepted installation and
  reinstallation; a saved-file sentinel and settings survived. Final-fix install
  additionally verifies the existing QA SQLite file remains byte-identical.

Task-harness issues are retained in raw logs but are not product defects: direct
synthetic wallet injection initially caused receipt-balance normalization; a
StringIO without an encoding disturbed Anki's console logging; and two probes
used outdated dashboard/enum assumptions. A popup probe also assumed the effects
row remains visible in compact mode; the final popup was checked directly with
that limit recorded. Corrected probes passed. Deliberate save failures are expected
error logs. An overstrict package probe rejected the intended user_files/README.txt
placeholder; the corrected inspection confirms no saved data is packaged.

## Completion gates

The final native archive passed identity gates, preserved the saved QA SQLite
file, processed another real answer, and opened/dismissed its effects popup.
The zero-card Activity display and subsequent one-day streak were verified on
the preceding archive; its only subsequent change removes two popup visibility/
reposition calls. The production archive has 266 entries and is 96,597,405 bytes.

- Immutable package: `build/functional-release-audit-20260907/verified-release.ankiaddon`
- SHA-256: `99a58f982185c4265ca2878f5dca8318d069cc02c0b3cdf1f10dc406e916c1b5`

The delivery copy in `dist` was superseded by a concurrent build. Use the immutable
audit archive for the exact native-tested bytes; later dashboard presentation
changes are outside this native package acceptance.

The complete release test **passed** after the final two obsolete ledger-version
assertions were updated to the production constant. It verifies 66 annual scenarios,
24,090 daily checkpoints, and 3,120,585 real-engine eligible answers, plus 98
bounded/randomized traces, 27 focused SQLite checkpoints, and durable restart,
duplicate-delivery, undo, and failed-save behavior.

The 66 annual engine replays were computed in three worker processes and saved
under `annual-cases/`; the existing release test then consumed those verified
results with catalog, reward-seed, day-count, answer-count, and relevant source
identity checks. The initial broad source guard stopped because a concurrent
dashboard edit changed an unrelated UI file. The final verifier excludes UI/hooks
from that engine guard and confirms the actual engine and simulator source stayed
unchanged. See `verified-release-test.log` and `complete-parity-result.json`.

The earlier default run had 1,731 passes and 21 skips with only this complete
release test failing; its final separate pass resolves that recorded failure.
The release-evidence lane had 800 passes and 37 skips. These are separate runs;
Qt and focused checks overlap and are not summed into a synthetic test total.

Windows/Linux native UI and the older supported Anki endpoint were not exercised.
No readily available Windows environment was found. Sync tests use synthetic
imported history, not an AnkiWeb account. Runtime timings were collected, but no
matched large-collection before/after latency claim is made. This functional pass
does not replace a full capture acceptance run or clear the pacing/human release
hold.
