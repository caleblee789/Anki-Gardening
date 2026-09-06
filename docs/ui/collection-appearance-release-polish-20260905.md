# Collection and Appearance release polish

Implemented the approved contact-sheet 2 changes for Anki Garden 2.2.0. The user decisions are authoritative: one plant can be owned per species, so Collection uses one detail panel. There is no individual-plant subpage, Back step, or plant selector. The latest requested removal of “Other active bonuses” from Appearance is implemented; equipment summaries now end the panel.

[Native review sheet](../../build/collection-appearance-overhaul/native-20260906-000518/native/contact-sheets/anki-garden-ui-contact-sheet-2.2.0-20260906-000736/01-collection-and-appearance.png) · [Per-surface validation](../../build/collection-appearance-overhaul/native-20260906-000518/native/surface-validation.json) · [Native manifest](../../build/collection-appearance-overhaul/native-20260906-000518/native/attempt/20260906-000736/manifest.json)

## Implemented changes

| Original surface | Problems addressed | Result |
| --- | --- | --- |
| 13. Plants collection | Small isolated cards above a large empty area; no useful selection state; highest-owned wording implied multiple plants | A selected-species gallery beside its detail panel. Cards use current-stage copy, clear artwork, consistent spacing, wrapping labels, and visible selection. Selection persists after refresh, and opening a stored plant reveals its selected card. |
| 14. Species details | Separate overview, redundant ownership count, repeated species/plant identity, ambiguous stage previews | One panel with location, Nurtured status, date added, direct actions, stage-relative Growth, a single stage gallery, and history. |
| 15. Plant details | Duplicate six-stage display and unnecessary navigation | Merged into the species panel. Historical plant deep links select the same panel. The historical capture ID now exercises a stored plant, rather than introducing another UI. |
| 16. Plant menu | Menu styling did not clearly belong to the surrounding UI; indirect actions and layered dialogs | A themed overflow menu in the same panel. Actions read “Move to another bed” and “Move to storage.” The existing restriction on storing the nurtured plant remains enforced. |
| 17. Storage confirmation | Stacked detail windows; unclear consequence; excessive shell complexity | A compact confirmation over the current Collection view names the plant and the bed that becomes empty. Success updates the same selection with inline feedback. |
| 18. Scenery | Separate appearance destinations; small preview; repeated actions; uneven cards and clipped descriptions | One Appearance tab with Scenery and Decorations categories, one shared garden preview, content-sized cards, and complete wrapped descriptions. |
| 19. Scenery preview | Repeated Equip controls and poorly distinguished preview/equipped state | Selecting a card previews it without saving. One nearby Equip action and Cancel preview control identify the temporary state. Equipped summaries continue to describe saved equipment. |
| 20. Applied scenery and Undo | Feedback far from its action; artwork and bonus state could appear unrelated | Equipment artwork and its effects commit atomically through the existing engine operation. Success feedback and Undo share a single row above the preview, leaving both equipped summaries fully visible at the normal window size. Failed saves preserve the preview for retry while keeping saved state unchanged. |
| 21. Decorations | Tiny art, sparse tall cards, redundant scenery layout | Compact decoration rows with clean thumbnails and the same preview/equipment model. No second appearance surface. |
| 22. Additional bonuses | Technical/repeated wording and poor use of the scrolling area | Removed completely from Appearance at the user’s request. The disclosure, its effect rows, and Plant supplies link no longer occupy the panel. Its historical capture ID is retired and reserved; underlying effects remain governed by the engine. |

The panels use the existing Garden palette and text hierarchy. Changes target layout, content bounds, and wording; they do not increase fonts across the application. Artwork thumbnails preserve aspect ratio and use the asset resolver’s high-resolution sources. Unintended frames around plants were removed. Scenery previews use the shared Garden compositor, including the other agent’s final lawn, lighting, shadows, and plant placement. Preview geometry follows the authored 3:2 canvas and remains bounded within its pane.

## Consistency rules retained

- Each species has one plant. “Current stage” describes that plant; a future stage image is a preview, never evidence of earned progress.
- The single stage gallery distinguishes Current, Next, Preview, Reached, and undiscovered Full Bloom. The existing Full Bloom reveal rule is preserved.
- Growth uses the engine’s stage-relative values and the shared “Growth toward…” formatter. Full Bloom does not offer Nurture.
- “In storage,” “Bed N,” and “Nurtured” come from committed state. Opening details does not change the nurtured plant. “Added” correctly describes the acquisition date for both placed plants and purchases still in storage.
- Scenery and decoration descriptions use the shared bonus projection. Items without an effect say “Appearance only.” Preview and saved equipment retain distinct meanings; Appearance shows no separate other-bonuses section.
- The visible navigation is Plants / Appearance. Older Scenery and Decorations routes select the corresponding Appearance category.
- The compact Collection view presents the same content in one dialog. The detail pane owns its scroll area so the parent Garden window cannot suppress access to stages or history.

## Verification and evidence

The final native snapshot is `build/collection-appearance-overhaul/native-20260906-000518/source`. Its matching production archive SHA-256 is `e70381adc847fe6bd6ea8022dcbe1c10629e21b40a3adfc9465204c816b94bc5`. The capture derivative SHA-256 is `20b791ff0020ad37013c58d4028c36f7ec444c02ba2ce9d2f540d4fb2b3c105e`. All 328 shared payload entries are byte-identical; [package parity](../../build/collection-appearance-overhaul/native-20260906-000518/native/package-parity.json) records the comparison.

Native Anki 26.8.1 ran in `/private/tmp/anki-release-qa.csce5vpn`, profile `Capture Full 20260906-000734`, with instance-key fingerprint `aeeed02f9b74`. Process, window, filesystem, and disconnected/sync-disabled gates passed. The disposable process exited normally with code 0. [Isolation evidence](../../build/collection-appearance-overhaul/native-20260906-000518/native/attempt/20260906-000736/isolation-gates.json) is retained. The normal profile was not used.

All nine retained native surface records pass capture acceptance and per-surface validation, with zero text/geometry warnings and no recapture requested for those records. The native images were reviewed for layout, copy, selection, menus, confirmation, preview, saved equipment, and the absence of the removed bonus section. The final applied-state image confirms both equipment descriptions remain completely visible after Equip. Final captures and their supplement use 1040 × 720; no further small-window capture was performed. The [native appearance supplement](../../build/collection-appearance-overhaul/native-20260906-000518/native/attempt/20260906-000736/garden-setup-supplement/setup-audit.json) also passes its checks for preview purity, matching catalog/equipment descriptions, atomic equipment effects, Undo, save failure, long descriptions, and complete catalogs.

Existing checks were reused:

- 72 existing transaction/environment/UI-copy/capture-contract checks passed after removal: [log](../../build/collection-appearance-overhaul/final-removal-backend-tests.log).
- 3 existing real-Qt layout checks passed: [log](../../build/collection-appearance-overhaul/final-removal-qt-tests.log).
- The final normal-size Qt review verifies the removed section, a single panel for both deep links, selected-card visibility, preview/cancel/equip/undo/failure state, complete equipped rows after saving, Full Bloom, storage success, and Nurture feedback: [results](../../build/collection-appearance-overhaul/qt-review-removal.json). The earlier [Qt review](../../build/collection-appearance-overhaul/qt-review.json) also covered compact dialog restoration. No new repository test suite was added.

The retired test asserting Landmarks inside the Plants catalog was removed because that surface is absent from the product. Existing Collection geometry assertions and the renamed appearance reference were updated. Capture metadata keeps stable surface IDs and points both plant/species routes to GardenDashboard. The removed bonus surface has no active route or sheet placement. The current full inventory is 50 surfaces across sheets of 12 / 9 / 12 / 10 / 7, with 22 representative surfaces. The capture auditor ignores deleted Qt scroll wrappers while still inspecting all current widgets; no visual gate was bypassed.

## Completion

The Collection and Appearance task is complete. All approved changes for this contact sheet are implemented, including the single plant/species panel and removal of Other active bonuses. Nine retained native views pass their checks, with no text or geometry warnings and no requested recaptures. The current UI code and its shared scene, copy, game, and asset-manifest dependencies match the verified snapshot.

The other threads were archived by the user. Completion of this task does not depend on reopening them or performing additional work for the other four contact sheets. No further implementation or verification is pending within this task’s scope.

The archived manifest retains its original aggregate incomplete/invalid status: this nine-view capture does not supply the full release inventory’s four-state scrolling witnesses. Its nine individual surface results are passed. Those historical aggregate results remain intact; this handoff records completion of Collection and Appearance and makes no claim of whole-release or publication approval.
