# Pre-release bug-testing execution — 2026-09-08

**Result: one ordinary-use defect fixed and reverified; functional acceptance remains open for three native checks.** Actual AnkiWeb sync, ordinary reviewing, supplies, milestones, companion add-ons, and sustained card performance passed the completed checks below. This is evidence for the frozen archive, not public release approval.

## Tested candidate and boundaries

- Final archive: [candidate-activity-fix.ankiaddon](../build/pre-release-bug-test-20260908-165056/candidate-activity-fix.ankiaddon).
- SHA-256: `6ef441bf1546300630bcff3d971ccaba4d7a9cde7e1bccd6a71e33457374d4c3`.
- 96,602,402 bytes; 267 entries. All 267 match the frozen source through the repository packager, including its generated manifest/capabilities bytes.
- Initial archive before the fix: `05b807b7ce23550001b8dc250325d314c0f3ce0d54a0bfd19b4201cb239e4a0d`.
- Frozen from the dirty checkout at `b3219e31181912d997796ee354a317cdb9373333`; subsequent source work reached `122d7541c0812d54d2cc78cc88ad99a1e843b33e`. Concurrent `ui/scene.py` edits are **excluded** from this candidate. The root distribution archive was not replaced; nothing was published or committed by this pass.
- Native target: macOS, Anki 26.08.1. Separate disposable bases and unique process keys were used. Gates recorded profile, process, collection location, sync state, and exact installed payload. Automatic and media sync stayed off. Manual sync used only the explicitly authorized test-account pair; the source had no Garden installed.

Evidence is under [build/pre-release-bug-test-20260908-165056](../build/pre-release-bug-test-20260908-165056/). Native answers, purchases, and settings changes used Anki controls. Separate QA helpers prepared fixtures and recorded state; they were not included in the production archive.

## Defect fixed

**Reopening remembered Activity showed stale totals after more reviews.** Close Garden on Activity, answer another card, and reopen: the wallet header updated, but Activity retained the old card/Growth/completion values. The observed stale display was 11 cards / 210 Growth / 56 Coins while saved state was 12 / 220 / 77 with today's cards complete.

`GardenDashboard._refresh_all_content()` tested child visibility during the hidden, pre-show refresh. It now refreshes the selected Progress, Collection, or Shop workspace even while its parent is hidden. The native recheck advanced 12 / 220 / 77 to 13 / 230 / 77 immediately on reopening, without another completion reward. See [dashboard.py](../ankigarden/ui/dashboard.py), `activity-fix-native-state.json`, and `responses/11-activity-fix-verified.json`.

No gameplay, API, schema, or economy changes were made. Existing tests were reused; no new tests were added.

## Journey results

| Journey | Status | Observed result and evidence |
|---|---|---|
| Current startup, package replacement, and saved progress | **Unverified in part** | Fresh onboarding, established-garden replacement, and repeated restarts passed. Replacement preserved the saved database bytes. Large-history startup completed verification and became ready. **A native answer while verification was still pending was not observed.** See `upgrade-install.json`, `restart-state.json`, `final-restart-state.json`, and `large-cards/*timings.json`. |
| Ordinary two-deck session | **Passed** | New cards, reviews, and actual learning repeats were studied. After deck A: 6 answers and 5 remaining obligations in B. At 11 answers, Anki waited for the final learning card and Garden showed 1 remaining; no completion reward. After the actual wait and final answer: 12 answers, 220 Growth, 77 Coins, and exactly one 16-Coin completion reward. Reviewer, Activity, and saved receipts were reconciled. See `after-first-deck.json`, `waiting-learning-state.json`, `completed-study-state.json`, and the Activity fix evidence. |
| Next Anki-day session | **Passed with fixture qualification** | Current Anki crossed a real configured 19:00 boundary. Its first subsequent card changed Rose 120→131 Growth, Fertilizer 100→99, and Coins 46→66. First-card +4 and completion +16 each appear once on each day; restart added nothing. The newly created collection's age was clamped at day zero across its first late boundary, so the disposable collection creation anchor was moved back one day before this review. No system clock or reward state was changed to manufacture the result. See `rollover/creation-anchor-correction.json`, `after-rollover.json`, and `restart-verified.json`. |
| Actual AnkiWeb sync | **Passed** | Source studied 30 actual cards; receiver advanced 22→52 eligible answers, Sunflower 0→330 Growth, and Coins 1945→1950, with one find. The native summary reported 30 cards / +330 Growth / +5 Coins / +1 find. The existing permanent bonus explains 11 Growth/card. Repeated sync changed no rewards or state. With the summary disabled, 3 more source answers arrived: 55 eligible, 363 Growth, 1950 Coins, no popup. Restart preserved the result. See `sync-thirty-state.json`, `sync-repeat-state.json`, `quiet-sync-state.json`, and `sync-source/`. |
| Common add-ons together | **Passed within stated compatibility behavior** | Review Heatmap 1.0.1, Homescreen Dashboard 1.8.7, Progress Bar 1.1.4, and Custom Background were installed together with Garden. Home content, Garden controls, keyboard answers, progress display, and rating buttons worked during four actual reviews. Dashboard deliberately pauses when Heatmap is enabled. A second session disabled Heatmap and exercised full Dashboard content, two more reviews, Garden/Collection access, and return to Home. Dashboard and Garden both reflected the new totals. See `companion-addons.json`, `combined-final-state.json`, `dashboard-after-study.json`, and `final-combined-state.json`. |
| Normal cards and sustained responsiveness | **Unverified in part** | **120 native answers passed:** 60 per HUD mode, stock Basic/Cloze and image cards, in a 37,683-card / initially 438,292-review-history collection. No repeatable answer or reveal stall appeared. Garden and Collection rendered and state survived restart. **The large-collection Activity interaction was not completed** because native window targeting repeatedly failed. See performance table below and `large-cards/restart-persistence.json`. |
| Supplies and milestones through reviews | **Passed** | Eight actual answers consumed Booster, then Basic Fertilizer, then queued Premium Fertilizer: Growth increments 16, 11, 13, 13, 10, 10, 10, 10. Stage transition occurred and exhausted supplies stayed exhausted after restart. Rose reached Full Bloom and Bed 4 unlocked. A clean subsequent native Sunflower Full Bloom run passed; final restart retained both 35,000-Growth plants and 62 main-profile answers. See `supply-native-events.json`, `full-bloom-state.json`, `final-combined-state.json`, and `final-restart-state.json`. |
| Live settings and window transitions | **Unverified in part** | Light→Dark, compact/expanded HUD, reward visibility, reduced animations, save/reopen, keyboard answering with rewards, Escape behavior, and macOS fullscreen entry/answer/exit were exercised. Final restart retained compact HUD, reduced motion, rewards on, sync summary off. **The minimum supported 860×580 window was not exercised**; the observed Garden size was 1040×720. |
| Anki 25.07 | **Passed bounded smoke; further testing stopped at user request** | Install→onboarding→two reviews→Fertilizer purchase→Settings→restart passed. Official PyPI `aqt==25.7`, Python 3.9, Qt 6.10.2; a disposable launch-wrapper instance-key shim isolated this older runtime. This is not evidence for the official bundled DMG. The initial unshimmed attempt exited with “Already running”; it did not open the normal collection in the test process. See `anki2507/responses/04-restart-verification.json`. |

Custom Background's default dark photograph reduced the contrast of Anki's own black text in Light mode. Garden remained legible; the Dark transition also rendered. This is a companion styling limitation, not a newly demonstrated Garden regression.

## Measured card performance

Native reviewer entry to two browser animation frames; timings exclude the automation tool's own delays. Both runs began after startup with their respective HUD mode selected. Each deck contained 61 cards so all 60 answers could render a subsequent question.

| HUD | Answer median / p95 / max | Reveal median / p95 / max | First reveal |
|---|---|---|---|
| Compact | 39.25 / 45.90 / 65.87 ms | 25.50 / 32.08 / 34.46 ms | 31.54 ms |
| Expanded | 36.30 / 45.84 / 58.06 ms | 38.07 / 45.70 / 50.55 ms | 32.83 ms |

Profile-open measurements were 962 ms and 918 ms. History became ready 12.08 seconds and 1.22 seconds after profile opening respectively. These are bounded observations on this Mac, not broad performance guarantees. The earlier expanded-HUD first-reveal stall did not recur. Raw observations and method: `large-cards/compact-timings.json`, `expanded-timings.json`, `native_observer.py`, and `timing-summary.json`.

## Automated validation and evidence qualifications

- Focused existing startup/history/sync/storage/reviewer/config checks: **266 passed**.
- Existing release-evidence suite: **800 passed, 37 skipped, 1778 deselected**. Skips are not native passes.
- Existing dashboard/UI/startup/Today's Cards checks after the fix: **142 passed**.
- Suites overlap; these are not additive unique-test counts. Final `git diff --check` and all 267 packaged payload comparisons passed.

QA setup/observer failures were kept separate from product defects. The older performance garden snapshot had a retired `garden_rhythm_percent` ledger column absent from both the preserved prior distribution and this candidate; it was preserved and replaced with a valid established QA garden for the performance run. Early database-only copying omitted SQLite journal updates, so the performance garden baseline is the verified copied state, not the receiver's latest total; final persistence readbacks include committed journal state. One Full Bloom observer incorrectly dereferenced an absent active plant after the transition; it was removed and the clean native transition rerun. Other helper assertion/API mistakes are retained in response logs and were corrected without production changes. Native capture/coordinate failures are tool limitations, not evidence of a product crash.

## Remaining acceptance work

1. On this exact archive, answer a normal card while startup history verification is visibly pending; confirm the notice clears and the answer receives rewards exactly once after restart.
2. Open and interact with Activity after the large-collection session. The ordinary-session Activity refresh defect is already fixed and reverified.
3. Resize Garden to its supported 860×580 minimum and exercise the primary navigation and review return.

Windows was not tested and VM provisioning was not undertaken. Linux remains unverified. The separate pacing and human release-approval holds remain unchanged. All disposable QA processes were closed; evidence and the user-created test account were retained.
