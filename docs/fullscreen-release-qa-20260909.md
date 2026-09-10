# Fullscreen release QA — September 9, 2026

Status: offline macOS QA completed and the local release package finalized, with the coverage limits below. The final settled HUD check passed and the isolated companion session closed normally. No public publication was performed.

The release owner authorized offline disposable-profile testing and a rebuilt package, without a commit, push, or publication. The current progression pace was explicitly accepted; this work does not rebalance rewards.

## Scope and isolation

Testing uses Anki 26.8.1 on macOS, temporary Anki bases, synthetic cards, disconnected accounts, disabled automatic/media sync, unique instance keys, and redirected Qt preferences. Normal collections and add-on configuration are excluded. Native fullscreen is verified by the observer, not inferred from window size.

Evidence is retained in `build/fullscreen-release-qa-20260909/`. The initial source snapshot and dirty changes are preserved there. Concurrent licensing and marketing changes were preserved. Only the three newly added package license files were incorporated into the frozen candidate after the runtime fixes.

## Confirmed defects fixed

1. Saving a garden name in Settings before choosing a starter completed setup prematurely and consumed the welcome-gift opportunity. Settings now renames without completing setup. The original native run reproduced the missing gift; the corrected native run retains setup version 0 after saving the name. The existing Qt welcome test now exercises naming before onboarding, checks the 51 Coins and 100 Growth gift, and retains its recovery/no-replay checks.
2. Purchase receipt formatting lowercased the remainder of the message, including the next sentence and named effects. Formatting now uppercases only the first character and preserves the remaining text.

3. The selected-plant supplies tooltip incorrectly called Basic Fertilizer “Magical Fertilizer.” The tooltip now uses the tier-neutral “Fertilizer”; verified in the reinstalled native package.
4. Repeated welcome-close requests reported a save error after the first acknowledgement had already succeeded. Repeating the same acknowledgement now succeeds without changing rewards; an existing atomic welcome/recovery test also verifies that a later “started” request cannot undo acknowledgement.
5. The completion banner repeated the same species name when one plant crossed multiple stages. The banner now lists distinct species names.

Existing Qt expectations were updated to match current painted control sizes, receipt actions, Growth labels, the cached supplies container, and the bounded diagnostics report. A misleading diagnostics scrolling comment was corrected. No new test files were added.

## Evidence collected

| Check | Current result |
| --- | --- |
| Initial default suite | 1,786 passed, 21 skipped, 846 deselected |
| Corrected Qt release suite | 845 passed, 1 skipped, 1,807 deselected |
| Final package and artwork-resolution checks | 17 passed; overlaps the Qt release suite |
| Corrected default suite | 1,786 passed, 21 skipped, 846 deselected in 25m 58s |
| Representative native capture | 23 of 23 raw surfaces; zero capture or text-layout failures; all 23 visually reviewed |
| Final archive representative capture | 23 surfaces, six contact sheets; clean native exit; six sheets visually reviewed |
| Final archive full audit | 53 of 53 surfaces; six sheets; shared production payload byte-identical; final six sheets visually reviewed with no additional issue identified |
| Hands-on fullscreen review | Again, Hard, Good, Easy; Undo and re-answer; session totals; expanded details; Continue studying; quit during review |
| Hands-on settings/onboarding | Name save, starter selection/back/placement/nurture; corrected pre-onboarding name save verified |
| Restart/reinstall | Clean restarts and package reinstall preserved name, welcome acknowledgement, Coins, Growth, and 99 remaining Basic Fertilizer cards |
| Large collection | 40,000 cards / 400,000 historical reviews; 142 native answers, including both Cloze cards; all due study cards completed; final revlog count 400,142; normal exit |
| Companion add-ons | Six-add-on baseline loaded; all four ratings and Undo/re-answer; background, Progress Bar, and Garden visible together; Heatmap rendered four reviews. HDO active mode separately rendered with Heatmap disabled. |
| Final follow-up tests | 76 focused tests passed; 845 Qt release tests passed, 1 skipped, in 40.40s |

The annual progression test exercises 66 scenarios over 365 days (24,090 day checkpoints) against the current engine and catalog. Its controlled initial fixtures are not a full reproduction of current welcome onboarding; separate current-onboarding parity tests and the native fresh/established flows cover that. It is useful consistency coverage, not a judgment of progression enjoyment. The full default suite, including annual parity, took 25m 58s. The last follow-up changes affect acknowledgement and display copy; focused and full Qt release checks were rerun, not the 26-minute annual suite.

## Capture checks and test limitations

Capture-only expectations were corrected for current session progress wording, and the geometry audit now omits a scene hotspot only when native hit-testing confirms a raised plant inspector occludes it. All inspector controls remain audited. These helpers are excluded from the production archive. Existing capture checks passed (40 tests); no new test files were added.

Dynamic memory probing was not run. A capture completion sentinel is not memory acceptance. The large collection run demonstrates functional completion, not an isolated performance benchmark: concurrent captures and computer-control round trips affect timing.

The Mac was manually unlocked after automatic unlock failed. Computer control also intermittently reported offscreen/no-window errors while Anki's observer remained healthy. Keyboard navigation and refreshing fullscreen placement restored interaction. One collapsed-HUD observation remained at an old percentage after a fullscreen transition; reopening the HUD restored current values and subsequent collapsed feedback updated. The final package completed 20 more collapsed-HUD answers with visible +10 feedback, including ten after capture finished. After manual unlock, the final settled HUD showed 85%, matching the observer’s 340 Growth toward the 400-Growth Sprout threshold at 24 reviews. Native Command-Q then exited normally with code 0. The earlier transient stale percentage was not reproduced in this final check; its origin remains unclassified, rather than being claimed as a fixed product defect.

The large profile briefly reported an acknowledgement save error, but its persisted receipt was acknowledged; the repeat-acknowledgement fix above addresses the demonstrated cause. Fresh-profile tests verified native Undo and re-answer do not duplicate reward or fertilizer consumption. Reward totals remained durable; pending session-summary presentation across restart has not been fully accepted.

Companion fixture setup initially omitted the background add-on's required `default_background` and `default_gear` folders. These were restored from bundled defaults; the failed setup attempts are preserved. No personal configs or credentials were copied. Network update checks failed locally as expected in the offline setup. AnkiHub account/sync workflows and Contanki hardware workflows are not covered by this run. Cross-platform and real server-sync testing remain outside its scope.

## Package

Production version: 2.2.0. Archive: `dist/anki_garden.ankiaddon`.

SHA-256: `ddcf540b21ca394fdfb1df0765239f6d9f38d4db5677e71d926284f97376ad20`.

The root and frozen-stage builders produce the same 271-entry, 96,632,375-byte archive. Production contains the license notices and excludes capture helpers. ZIP integrity and whitespace checks passed. The packaged asset manifest and build-capability payload are generated by the builder; raw-source byte comparison must account for those generated entries. No commit, push, or public publication was performed.

## Final capture artifacts

Anki Garden 2.2.0, capture contract v29, 53 surfaces, six contact sheets, canonical 100% scale on the primary display. Capture derivative SHA-256: `35e5dcef493821036fb88a4337af2c1ccf19ff5abb8ddb246a79761d0ab006c2`. Shared payload proof: 270 byte-identical entries; only the capture subtree and explicit build capabilities differ. Detailed capture status remains immutable; this report and the visual-review ledger record the subsequent sheet review.

- [01 garden and onboarding](</Users/test/Documents/Anki Gardening.nosync/build/fullscreen-release-qa-20260909/captures/full/contact-sheets/anki-garden-ui-contact-sheet-2.2.0-20260909-214737/01-garden-and-onboarding.png>)
- [02 collection and appearance](</Users/test/Documents/Anki Gardening.nosync/build/fullscreen-release-qa-20260909/captures/full/contact-sheets/anki-garden-ui-contact-sheet-2.2.0-20260909-214737/02-collection-and-appearance.png>)
- [03 shop and item use](</Users/test/Documents/Anki Gardening.nosync/build/fullscreen-release-qa-20260909/captures/full/contact-sheets/anki-garden-ui-contact-sheet-2.2.0-20260909-214737/03-shop-and-item-use.png>)
- [04 progress and settings](</Users/test/Documents/Anki Gardening.nosync/build/fullscreen-release-qa-20260909/captures/full/contact-sheets/anki-garden-ui-contact-sheet-2.2.0-20260909-214737/04-progress-and-settings.png>)
- [05 anki integration and rewards](</Users/test/Documents/Anki Gardening.nosync/build/fullscreen-release-qa-20260909/captures/full/contact-sheets/anki-garden-ui-contact-sheet-2.2.0-20260909-214737/05-anki-integration-and-rewards.png>)
- [06 plant beds](</Users/test/Documents/Anki Gardening.nosync/build/fullscreen-release-qa-20260909/captures/full/contact-sheets/anki-garden-ui-contact-sheet-2.2.0-20260909-214737/06-plant-beds.png>)
- [Contact-sheet index](</Users/test/Documents/Anki Gardening.nosync/build/fullscreen-release-qa-20260909/captures/full/contact-sheets/anki-garden-ui-contact-sheet-2.2.0-20260909-214737/contact-sheet-set.json>)
- [Raw manifest](</Users/test/Documents/Anki Gardening.nosync/build/fullscreen-release-qa-20260909/captures/full/capture-sequence-20260909-214737/assembled/manifest.json>)
- [Capture report and derivative proof](</Users/test/Documents/Anki Gardening.nosync/build/fullscreen-release-qa-20260909/captures/full/capture-sequence-20260909-214737/capture-report.json>)
- [Capture archive](</Users/test/Documents/Anki Gardening.nosync/build/fullscreen-release-qa-20260909/captures/full/anki-garden-ui-faces-20260909-214737.zip>)

The final companion session (PID 99848) passed settled fullscreen HUD inspection after manual unlock: 85% matched 340/400 Growth, with 24 recorded reviews and 57 Coins. Native Command-Q exited with code 0. Fresh, large, and final companion sessions have verified normal exits. The final production archive hash was rechecked unchanged after shutdown.
