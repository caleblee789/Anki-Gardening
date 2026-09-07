# Activity polish — 6 September 2026

Progress → Activity now uses a wide activity feed and a stacked reward sidebar. Four compact Today metrics sit above them. The feed takes about 70% of the lower area, allowing for a readable 320 px sidebar. At compact widths, the reward cards move above the feed and share a row when they fit; smaller layouts stack them. The page owns scrolling, and Show more extends the history. There is no separate feed scrollbar or shop footer.

Sessions use two compact rows: Study session with recorded times and duration, followed by inline Card answers, Growth, Coins, and Finds. Optional zero rewards are omitted. Purchases say Bought followed by the saved item name, with the amount aligned right and the time underneath. The filters form one compact control beside the feed heading and wrap below it when necessary. Existing icons, theme colors, typography, and wrapping controls provide the presentation.

## Reward meaning and accuracy

- Card answers count answer events, including repeat answers to one card. They do not imply unique cards or completed due work.
- Finish all due cards shows the actual recorded Coin amount and Earned independently of the current workload. More cards becoming due, or unavailable card status, does not revoke the earned state.
- The canonical completion counter counts distinct qualifying Anki days. Completed days and its progress segments use the engine's threshold; these days need not be consecutive. The recurring bonus is displayed separately from the all-due amount. The existing combined reward calculation and grant path are unchanged.
- First card today uses the saved payout. The next streak milestone and its amount come from the shared reward presentation. Reward details contains cumulative recorded payout totals.
- Daily totals remain independent of feed filtering and pagination. Coins earned represent receipts before spending; the header shows the current balance. Unavailable totals display an em dash instead of an invented zero.
- Session times are formatted from their recorded bounds. Open, interrupted, and incomplete historical records do not acquire invented end times or durations. Date groups use the Anki day, with Today and Yesterday headings.
- Existing atomic activity storage, source grouping, payout deduplication, purchase naming, and session identities remain in place. Hovering over a session stat exposes the recorded source or destination breakdown.
- History errors provide Try again. Empty filters have specific messages. Loading does not show zero rewards or earned badges. Expanded details and long item names wrap in the page flow.

## Changed files in this polish pass

| File | Change |
| --- | --- |
| `ankigarden/ui/activity_page.py` | Layout, compact feed, reward wording and states, shared theme typography, progress segments, history retry, and wrapping. |
| `ankigarden/ui/dashboard.py` | Optional responsive split proportions/order/minimums; unavailable Find total; current-balance tooltip. Existing split defaults are preserved. |
| `ankigarden/ui/controls.py` | Shared inline wrapping layout. Activity also reuses the existing GardenWrappingLabel. |
| `ankigarden/ui/formatters.py` | Recorded session range/duration and Anki-day activity headings. |
| `ankigarden/game.py` | Adds separate completion amount and cycle-earned fields to the read-only reward summary. No reward calculation, grant, or saved-data change. |
| `tests/test_engine.py` | Extends the existing nonconsecutive completion-cycle check to cover separate amounts and an earned reward after more work becomes due. |
| `tests/test_formatters.py` | Covers recorded/missing/reversed session times and Anki-day date headings. |
| This document | Current implementation, captures, and acceptance evidence. |

## Captures and verification

Final evidence is in `build/activity-polish-20260906/native-verified`. The earlier attempts remain available separately and are not the final acceptance evidence.

- [Normal layout](../../build/activity-polish-20260906/activity-normal.png): 1040 × 780 logical pixels.
- [Compact layout](../../build/activity-polish-20260906/activity-compact.png): 860 × 780, the existing native workspace minimum width.
- [Compact layout, scrolled to the last session](../../build/activity-polish-20260906/activity-compact-bottom.png).
- [Expanded details](../../build/activity-polish-20260906/native-verified/state-expanded.png) and [bottom of the expanded page](../../build/activity-polish-20260906/native-verified/state-expanded-bottom.png).
- [Long names and large values](../../build/activity-polish-20260906/native-verified/state-long-history.png).
- [Verification report](../../build/activity-polish-20260906/verification.json), [state captures](../../build/activity-polish-20260906/native-verified/states-report.json), and [package parity](../../build/activity-polish-20260906/package-report.json).

The focused ledger, reward, formatting, theme, layout, and interaction suite passed 176 checks. Six existing completion checks passed separately. The broader session/reward/HUD run passed 79 checks and found one pre-existing Mastery failure, reproduced with the engine copied before this polish pass: `test_engine_committed_result_owns_standard_find_count` expects Growth routed to the disabled Mastery feature.

Native macOS Anki 26.8.1 ran at normal text scale in a fresh sync-disabled profile. The process, window, filesystem, and sync isolation checks passed on launch and controlled restart. The run committed two real 24-answer sample sessions, a welcome gift, and a purchase. Saved session times, source totals, and the earned reward survived restart. The final default data shows 48 answers, 580 Growth, 67 Coins earned, one Find, and a 37-Coin balance after the 30-Coin purchase.

Completed, earned-with-more-due, incomplete, no-due, unavailable, empty, loading, retry, and expanded states were reviewed. A 25-entry fixture verified Show more and the final event's reachability. Normal, compact, long-name, and expanded captures have no detected label clipping or horizontal scrolling. The disposable app exited cleanly after both runs. The normal profile and existing release archive were not replaced.

No Activity layout or wording issue remains known from this review. This is scoped Activity acceptance; a full release-wide capture/test run and human release approval are not claimed. The unrelated Mastery assertion remains open.
