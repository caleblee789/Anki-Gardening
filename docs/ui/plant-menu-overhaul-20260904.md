# Nurtured-plant bar and floating menu — September 4, 2026

Implemented the approved Garden follow-up on top of the existing uncommitted redesign. The bottom bar tracks the **nurtured plant**; the floating menu tracks the **selected plant**. Inspection never changes where Growth goes.

## Result

The summary remains 72 logical pixels high in the native layout matrix. It has a 40 px artwork area, an eliding name with its full tooltip, a quiet Nurturing label, stage/Growth text, and a slim progress track. The identity and progress group is bounded to 480 px. **View plant** is its only action when a plant is nurtured.

The floating menu prefers 304 px width and sizes to its content. Its Close control stays above one local scrolling content region. Growing nurtured plants show **Use item…**, Move, Details, and More → Stop nurturing. Other growing plants show **Nurture**, Move, and Details. Completed plants show Full Bloom once, omit next-stage progress, and offer **Choose another plant**, Move, and Details.

Hover highlights plants. Clicking selects or toggles their menu; View plant opens the nurtured plant and stays open on repeated activation. Background click, Close, Escape, and leaving Garden dismiss the menu. More and owned dialogs handle their own Escape first. Move hides the menu and restores the selected plant after completion or cancellation. Routine refreshes update existing selection without reopening a dismissed menu.

With no nurtured plant, the bar says **No plant is being nurtured** and offers **Choose plant** through the existing selection flow. Starter selection and initial placement hide the bar. Committed nurture, item use, rename, Growth, and Undo continue through the existing refresh boundary; failed saves retain committed state.

The existing placement resolver and connector are active again. Overlays can use the space surrounding a letterboxed scene image while plant and bed geometry remains unchanged. This resolves the constrained bed-4 placement without covering the selected artwork. Popup scrolling remains independent of the main Garden page.

Engine APIs, saved-state schemas, progression, rewards, and item eligibility are unchanged. The [entry-point matrix](entrypoint_matrix.md) documents the current routes.

## Verification

| Check | Result |
| --- | --- |
| Existing focused UI, geometry, display, transaction, package, theme, and capture checks | **304 passed, 11 skipped, 1 deselected** in 32.12 seconds. The standard environment lacks Anki Qt; the frozen historical-contract test was excluded from this focused rerun. |
| Selected live Qt state and interaction tests | **2 passed** in 2.15 seconds using the installed Anki Python/Qt runtime with the offscreen platform. |
| Full native capture | **36/36 surfaces**, fresh captures, independently validated; zero audit advisories and text-layout warnings. |
| Six-bed native layout matrix | **18/18 cases** across **1040 × 720**, **860 × 580**, and **1440 × 900**; bar height **72 px** throughout. Selected plants remain clear; menus fit within the scene and retain their local scrolling policy. |
| Contact sheets | **5/5 pages**, covering all 36 surfaces; validated and reviewed. |
| Package parity | **321 shared payload files byte-identical**; production dashboard and scene also match the current source. |
| Disposable profile | All **nine isolation checks passed**; sync disconnected and disabled; Anki exited cleanly with code **0**. The recorded process was confirmed absent afterward. |
| Working-tree check | `git diff --check` passed. |

The reused state matrix checks zero, partial and complete stage progress, active fertilizer status, other growing plants, Full Bloom, long names, missing artwork, and constrained scrolling. One essential interaction test covers inspecting B while nurturing A, dismissed refreshes, repeated View plant, More and owned dialogs, Move cancellation, keyboard reopening, explicit nurture/Undo, tab dismissal, and choosing without automatic nurturing. Existing selection and transaction tests retain click, movement, Undo, rollback, and save-boundary coverage. No new test files were added.

The 304-test run preceded the final copy-only change from “Choose next plant” to “Choose another plant” in this menu. Both live Qt tests and the complete native capture ran after that change. Earlier overlapping checks are retained in the task folder and are not added to these counts.

Native evidence uses **Anki 26.8.1**, the primary macOS display, **100% Qt scale**, and **2× device pixel ratio**. All five final sheets were visually reviewed, with raw-image follow-up on Garden inspection, Move, item use, Full Bloom, and the narrow/large layouts. No blocking visual defects were identified in this scope. This does not claim other operating systems, additional scaling configurations, a full unrelated engine-suite run, or human release acceptance. `quality_status` remains `review-required` and `release_ready` remains `false`.

The [verification record](../../build/plant-menu-overhaul-20260904-181804/verification-results.json) contains commands, logs, and exact results. The [agent visual review](../../build/plant-menu-overhaul-20260904-181804/agent-visual-review.json) records reviewed images and hashes. The [native layout audit](../../build/plant-menu-overhaul-20260904-181804/native-full/full/capture-sequence-20260904-190142/attempts/01-capture-session/20260904-190337/plant-menu-layouts/layout-audit.json) contains all 18 screenshots and measurements, and the [isolation record](../../build/plant-menu-overhaul-20260904-181804/native-full/full/capture-sequence-20260904-190142/attempts/01-capture-session/20260904-190337/isolation-gates.json) identifies the disposable run.

## Rebuilt package and evidence

| Artifact | Identity |
| --- | --- |
| [Production snapshot](../../build/plant-menu-overhaul-20260904-181804/native-full/full/capture-sequence-20260904-190142/production/anki_garden.ankiaddon) | Version **2.2.0**, **322 files**, **100,403,653 bytes** |
| Production SHA-256 | `3a89d2426282485bfc2743160ea22d3157cb4e6d885b1c607e42ade82919e3c6` |
| [Capture derivative](../../build/plant-menu-overhaul-20260904-181804/native-full/full/capture-sequence-20260904-190142/anki_garden_capture.ankiaddon) | **337 files**, **100,839,411 bytes** |
| Capture SHA-256 | `f3fecf791e278e8a8e20734357cd3f5eaddfda577e2616d6ee5854c9428151ec` |
| Shared payload SHA-256 | `cc17b1d0f03b33a39f3981f9ec3e17424990ca210b8686952604dab0c8e4fc99` |
| [Evidence archive](../../build/plant-menu-overhaul-20260904-181804/native-full/full/anki-garden-ui-faces-20260904-190142.zip) | **65,519,609 bytes**; raw and assembled captures, layout matrix, sheets, reports, and logs |
| Archive SHA-256 | `e6f995fa71fd2893fecdd42c037adfbccc27cfd2862b5c5e72813f27ba71b225` |

The production snapshot and capture derivative are preserved separately from the evidence archive. The [capture report](../../build/plant-menu-overhaul-20260904-181804/native-full/full/capture-sequence-20260904-190142/capture-report.json) includes package-derivative parity and independent surface/contact-sheet validation. The [assembled manifest](../../build/plant-menu-overhaul-20260904-181804/native-full/full/capture-sequence-20260904-190142/assembled/manifest.json) is the authoritative 36-surface inventory; the [contact-sheet index](../../build/plant-menu-overhaul-20260904-181804/native-full/full/contact-sheets/anki-garden-ui-contact-sheet-2.2.0-20260904-190142/contact-sheet-set.json) binds tiles to their captured sources.

| Contact sheet | Surfaces |
| --- | ---: |
| [First run and Garden](../../build/plant-menu-overhaul-20260904-181804/native-full/full/contact-sheets/anki-garden-ui-contact-sheet-2.2.0-20260904-190142/01-first-run-garden.png) | 10 |
| [Collection](../../build/plant-menu-overhaul-20260904-181804/native-full/full/contact-sheets/anki-garden-ui-contact-sheet-2.2.0-20260904-190142/02-collection.png) | 6 |
| [Shop](../../build/plant-menu-overhaul-20260904-181804/native-full/full/contact-sheets/anki-garden-ui-contact-sheet-2.2.0-20260904-190142/03-shop.png) | 7 |
| [Progress and Settings](../../build/plant-menu-overhaul-20260904-181804/native-full/full/contact-sheets/anki-garden-ui-contact-sheet-2.2.0-20260904-190142/04-progress-and-settings.png) | 6 |
| [Anki and rewards](../../build/plant-menu-overhaul-20260904-181804/native-full/full/contact-sheets/anki-garden-ui-contact-sheet-2.2.0-20260904-190142/05-anki-and-rewards.png) | 7 |

Cream padding is part of the contact-sheet presentation. The pending visual-review caption refers to human acceptance; the agent review is recorded separately.

Prior production archives, historical captures, the preexisting dirty tree, and intermediate task evidence are preserved. The [task-only patch](../../build/plant-menu-overhaul-20260904-181804/implementation.patch), [initial tracked diff](../../build/plant-menu-overhaul-20260904-181804/worktree-before.patch), and [initial status](../../build/plant-menu-overhaul-20260904-181804/status-before.txt) separate this follow-up from the earlier redesign. No commit, publication, or release approval was performed.
