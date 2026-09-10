# Reviewer regression fixes — 2026-09-09

Fixed against `6e9e679175c64f2e7fee5666b57f941ebeef2f1b`, the previous UI/review-flow commit. Changes are uncommitted. The pre-existing, untracked marketing ZIP was preserved.

## Causes and corrections

- **Expanded HUD clipping:** the extra nested session-footer padding, fixed plant artwork, and pinned reward feed could exhaust the plant viewport. Against the previous build, opening the feed with a 480-pixel reviewer surface put the Growth label's bottom at 185 pixels in a 154-pixel viewport. The corrected layout reserves room for the text and footer, removes redundant inner padding, and reduces only plant artwork when necessary. Long Growth labels wrap. HUD width remains 296 pixels; native UI scale is unchanged.
- **Delayed local feedback:** background reconciliation committed deferred local answers without delivering their results to the reviewer accumulator. Those results now update their matching active or saved session. A session started while verification is pending also retains its identity when verification finishes, preserving its Growth totals and reward feed.
- **Quit during reviews:** summaries previously depended on leaving the review screen and existed only in memory. Confirmed collection closure now saves the unshown local session in its Anki profile, after cancellable close dialogs and before collection teardown. Reopening waits for reconciliation, incorporates matching deferred answers, and presents a Session Summary once. Profile changes, cancellation, queued sessions, and navigation before presentation preserve the appropriate boundaries.
- **Local versus sync summaries:** local and locally recovered answers are excluded from Sync Summaries. Mixed batches use the committed remote answer facts, preventing local balance changes from entering the downloaded-reward receipt. This changes presentation and session accounting, not reward calculations.
- **Checkpoint:** restored the existing painted golden diamond for the next reviewer checkpoint.
- **Consumable badges after expansion:** native QA exposed an additional related visibility defect. Projection updates while collapsed hid the fertilizer/booster container itself, so expanding an unchanged projection could leave it hidden. The expanded parent now owns collapse visibility; existing layout coverage checks that both active badges remain visible after re-expansion.
- **Startup before profile selection (follow-up):** the user reported `Anki Garden failed to start: 'NoneType' object has no attribute 'get'` after reinstalling. The new recovery reader assumed an existing `pm.profile` was a dictionary, but Anki can set it to `None` while importing add-ons. The exact exception was reproduced in the existing recovery test. Both reading and saving now tolerate no selected profile; the already-registered profile-open hook restores the session once a profile is available. That later hook explains why Garden could appear functional despite the warning. The explicit-profile native launches above did not cover this startup order.

## Verification

- **296 passed:** existing interaction, session-summary, summary-card, sync processor/presenter/detector, history, reviewer HUD, and startup/close suites, including the added recovery cases. Command:

  ```text
  .venv/bin/python -m pytest tests/test_ui_interaction_regressions.py tests/test_session_summary.py tests/test_session_summary_integration.py tests/test_session_summary_card.py tests/test_sync_reward_processor.py tests/test_sync_reward_presenter.py tests/test_sync_review_detector.py tests/test_history_index.py tests/test_reviewer_hud.py tests/test_addon_startup_and_home.py -q
  ```

- **9 passed:** `tests/test_live_ui_layout.py -m release_evidence`, using Anki's installed Qt runtime with the offscreen platform. Covers the short HUD from expanded, collapsed, and initially hidden states, reward-feed visibility, wrapping, and the other existing layout checks. The previous HUD fails the same short-viewport assertion.
- **Native macOS / Anki 26.08.1:** a fresh disposable profile with sync disabled answered a card, quit directly from the review screen, and reopened to **Session summary**, **1 card**, **+10 Growth**, with no pending Sync Summary. That first fixture earned Stored Growth. After the Mac was unlocked, the packaged lifecycle fix was tested again with a flowering plant: the HUD showed **+13 Growth**, the details feed matched, and reopening restored the **same session ID**, **1 card**, and **+13 Growth**, with its saved receipt cleared and no pending Sync Summary. The final package also passed the native fertilizer collapse/expand check. Both full-size and 667×602 native windows were inspected. The normal profile was not modified, and the isolated process was closed after testing.
- `git diff --check` passed. Package payload parity is recorded separately below.
- **Startup follow-up: 150 passed** across session integration, startup/close, sync processor and presenter tests. The existing recovery test now begins with no selected profile, then verifies normal save/reopen recovery. This follow-up was verified automatically; the preceding native observations apply to the package before this small profile guard was added.

## Quick audit of the other previous-commit changes

Reviewed the changes to Activity scrolling, garden selection and decoration hit targets, Plant Beds badges, Trophy Room text/layout, reward receipts, dashboard navigation, and review continuation, alongside their existing interaction/layout checks. No additional regression attributable to the previous commit was established.

The broader Qt run reported **29 passed, 1 skipped, 5 failed**. All five failures also reproduce against `38a7478`, before the previous commit: two stale wording expectations, one brittle popover child-index assumption, an existing settings-detail height failure, and an existing 380-pixel / 2× welcome overflow. They were kept outside this repair's scope. See [baseline output](../build/reviewer-regression-20260909/prior-commit-ui-baseline.txt).

This is targeted regression evidence, not an all-platform release sign-off. A full default-suite attempt was stopped during the long balance checks; it is not counted as passing. Windows, Linux, actual remote sync, and the final combined candidate's remaining broader release gates were not exercised here.

## Updated production package

- [anki_garden.ankiaddon](../dist/anki_garden.ankiaddon)
- SHA-256: `6b6982ffbca389a23c1f4312ebad39c0b77c7f1d23e5bff1fec0dafdc6890437`
- 96,611,238 bytes; all 268 entries match the current production packager payloads.
- [Latest package parity](../build/reviewer-regression-20260909/startup-guard-package-parity.json). The earlier native candidate had SHA-256 `4892ea2912a7f5f1cd566f9c06810966988329c6750698892eff72b4e2acc251` and matched its isolated installation.
- [Package parity and native readbacks](../build/reviewer-regression-20260909/).

Nothing was committed, installed in the normal profile, or published. The isolated QA window was closed; its evidence remains available.
