# Anki Garden 2.2.0 UI redesign

This implements the contact-sheet review of the 34 surfaces in the September 1, 2026 `002050` evidence set. The earlier captures and their report remain historical evidence. They do not describe the redesigned UI.

The initial redesign's implementation, focused verification, and native capture were completed on September 4, 2026. Its 36 surfaces and five contact sheets passed validation. The verification and package identities below describe that initial captured candidate. The later plant-bar/menu follow-up updates the Garden behavior described here; its evidence is recorded in the [plant-menu verification report](plant-menu-overhaul-20260904.md). Human release acceptance remains separate from these results.

## Organization

The Garden is one window with persistent Garden, Collection, Shop, and Progress tabs. Secondary pages are ordinary widgets within that window. Popups are reserved for individual plant/species details, Settings, item use, confirmations, and rewards.

| Area | Change and purpose |
| --- | --- |
| Global navigation | Keep the same four tabs, garden name, coin balance, and Settings gear in every main page. Repeated entry points select the same destination. |
| Garden | Keep a compact bottom summary of the nurtured plant with one View plant action. Clicking any plant opens its floating menu for inspection and actions. Retain the scene and placement controls. |
| First run | Offer four free plants inline. Use one explicit Choose plant action, followed by placement and nurture. Remove the separate catalog/confirmation journey and repeated setup explanations. |
| Collection | Use Plants, Scenery, and Decorations. Remove redundant category/filter controls and combined catalog-entry counts. Species counts remain useful on the Plants page. |
| Shop | Use Plants, Supplies, Scenery, and Decorations. Replace large purchase cards and actions with compact rows. Show ownership beside each item. Earned beds belong in Progress, not among purchases. |
| Progress | Combine daily cards and streak information in Today. Keep Achievements and Coins as separate pages. Put detailed rules and active/queued effect explanations behind Details. |
| Settings | Keep naming and ordinary display/reward toggles together. Remove the repeated appearance summary. Collapse Diagnostics within the same scroll area. Keep Save and Cancel explicit. |
| Appearance | Equip owned scenery/decoration with one action that selects both artwork and effect. Apply commits previews; Undo restores the previous equipment. Show the item’s effect without timing or scheduling controls. |
| Item use | Group owned Fertilizer and Growth Charges in a target-specific dialog. Preserve the plant when opening Shop supplies. Refresh inventory after use. |
| Plant bar and menu | Keep nurturing independent of selection. The 72 px summary tracks the nurtured plant; the 304 px floating menu tracks the clicked plant and stays closed after dismissal, including during Growth refreshes. |
| Plant details | Keep name, species/stage, stage artwork, next-stage progress, and actual memories. Remove repeated current/required Growth lines and empty history sections. |
| Species overview | Fit the six growth stages within a focused dialog; keep undiscovered Full Bloom art hidden. Remove clipped Full Bloom metadata and unused grid columns. |
| Rewards | Keep the HUD at 296 px wide. Use 400 px summaries with content-driven height and Details for additional information. Remove redundant confirmation/reassurance text. |

## Visual rules

- Retain the garden-green palette, restrained mint selection/action accents, and gold for Coins. Keep visual states distinct without assigning bright colors to every section.
- Use a 48 px main header, compact secondary navigation, and content-width actions. Standard actions are 28–32 px; the main tabs are 34 px. Art selection tiles are separate from action buttons.
- Keep the default main window at 1040 × 720, with an 860 × 580 minimum and screen clamping. Changing tabs must not resize it. Long catalogs scroll rather than enlarging the window.
- Fit popups to their content: Settings around 600 px wide, item use around 560 px, purchase/Growth Charge dialogs around 480 px, and plant/species details around 660 px. Apply screen limits rather than forcing large fixed windows.
- Prefer 8–16 px gaps, modest card padding, and compact 48 px item artwork. Remove empty rows and repeated headings. Keep useful negative space around the garden artwork instead of filling it with instructions.
- Keep the existing ordinary text scale. Resolve clipping with layout, wrapping, elision/tooltips, or shorter copy rather than increasing font sizes.
- Use one visible scroll owner per page or popup. Keep primary actions and navigation outside the scrolling catalog. Preserve explicit empty states and error recovery.

## Copy and actions

| Prior wording or pattern | Current direction |
| --- | --- |
| Nursery as a destination | Shop; retain internal route IDs for compatibility. |
| Garden Progress with six overlapping pages | Progress: Today, Achievements, Coins. |
| Separate Fertilize and Growth Charge inspector buttons | Use item. |
| Story / Plant Story | Details / Plant details. |
| Combined Garden Decorations and Scenery | Separate Scenery and Decorations tabs. |
| Combined species and catalog-entry coverage | Plant species discovered. |
| Dormant Landmark feature | No tabs, appearance controls, artwork, or reward mentions. Preserve backend and saved data. |
| Eligible/newly processed card implementation language | Cards studied/completed in ordinary presentation; detailed rules stay in Details where needed. |
| Duplicate reward-applied reassurance | Omit it. Close and Open garden are sufficient. |
| Hidden artwork conflated with inactive effects | Display controls and bonus selection have separate labels and actions. |

Visible copy must add information needed to understand a state or make a decision. Omit generic selection or nurture instructions when the controls, ownership count, or plant context already make them clear; do not repeat them in every item row. Keep precise effects, limits, timing, costs, consequences, and restrictions that are not apparent from the controls. Disabled controls retain their accessible explanation without adding repeated visible helper text. An empty or locked state needs prose only when its next useful action is not already clear. Technical diagnostics may retain technical terminology inside their disclosure.

## Behavior retained

Prices, inventory, Growth, daily locking/queues, purchase quotes, reward processing, and persistence remain owned by the existing engine. Appearance Undo changes only the fields changed by that appearance action and preserves unrelated newer choices. Purchases keep their explicit target and confirmation boundary. Failed saves retain the last committed state.

Booster Potion applies to the nurtured plant. It is not presented as a garden-wide consumable. Hiding a decoration does not deactivate its bonus.

## Proportional verification

Reuse the existing transaction, persistence, navigation, geometry, and reward checks. Update obsolete tests that only enforce retired markup, old control dimensions, or removed filters. Retain placement and selection coverage for the restored floating menu. No new test suite, broad accessibility audit, or enlarged typography is required by this redesign.

The v27 capture contract contains 18 representative surfaces and 36 full surfaces, presented in two and five contact sheets. New page routes use the actual persistent window and focused dialogs. Production and capture packages retain byte-matched shared payloads; old contracts, captures, and the previous production archive are preserved.

## Verification results

| Check | Result |
| --- | --- |
| Existing focused UI, transaction, reward, theme, economy-view, package, and capture tests | **266 passed, 2 skipped, 1 deselected** in 32.18 seconds. The two skips require an Anki runtime; the native run below separately exercised the packaged UI. |
| Follow-up after final compact Shop rows, achievement spacing, and scroll-contract adjustments | **135 passed, 1 deselected** in 19.36 seconds. This overlaps the focused set and is not an additional unique-test count. |
| Frozen historical contract/scenario identity check | Passed earlier in the implementation. Excluded from the two fast reruns above. |
| Native v27 full capture | **36/36** surfaces; independent manifest validation valid; no capture failures, audit advisories, or text-layout warnings. |
| Scroll coverage | Existing no-overflow, one-row, long-list, and final-item checks passed. Hidden pages do not count as visible scroll owners. |
| Contact-sheet validation | **5/5** pages, covering all 36 surfaces with source/fixture/scenario identity retained. |
| Agent visual review | All five final sheets reviewed, with raw-image follow-up on critical layouts. No blocking visual defects identified in this scope. |
| Production/capture parity | **321 shared payload files byte-identical**. Capture-only files are excluded from production; the one mode-specific capability file is explicitly accounted for. |
| Disposable-profile identity and shutdown | All nine isolation checks passed, sync disabled, and Anki exited cleanly with code 0. |

The focused tests retain purchase totals, rollback, reward identity, deduplication, and saved-state behavior. Removed tests prescribed retired filters, floating inspector placement, old button dimensions, or source/markup structure without protecting a continuing behavior. No new test files were added. Real defects found during native review—such as clipped text, displaced controls, excessive row height, and hidden-page scroll accounting—were corrected and recaptured.

The full unrelated engine simulation suite was not completed for this UI change; no full-suite pass is claimed. Additional checks during implementation exercised all nine main routes, focused popups, and appearance/Undo against the real engine without changing Coins, inventory, or the locked bonus.

The final run used **Anki 26.8.1**, embedded Python **3.13.14**, the **primary macOS display**, **100% Qt scale**, and **2× device pixel ratio**. The Anki host was maximized to 1710 × 1041 logical pixels; Garden pages remained 1040 × 720. This is not evidence of macOS full-screen Spaces behavior. Other operating systems and additional display/scaling combinations were not verified in this run. No broad accessibility test program was added.

The test commands and durable logs are in the [verification record](../../build/ui-face-captures/full/capture-sequence-20260904-173751/verification/verification-results.json). The visual review scope and page hashes are in the [agent visual review](../../build/ui-face-captures/full/capture-sequence-20260904-173751/agent-visual-review.json).

## Packaged candidate and evidence

| Artifact | Identity |
| --- | --- |
| Production add-on preserved in the [historical evidence archive](../../build/ui-face-captures/full/anki-garden-ui-faces-20260904-173751.zip) | Version **2.2.0**, **322 files**, **100,401,696 bytes** |
| Production SHA-256 | `f716246986af0fe95a057b4583c295dc585152ede776536e7e9406c5f9495a55` |
| [Capture derivative](../../build/ui-face-captures/full/capture-sequence-20260904-173751/anki_garden_capture.ankiaddon) | **337 files**, **100,836,324 bytes** |
| Capture SHA-256 | `502b20118862566b5aab976a4389268c69a9a69fd95ef9ce51b58549216b3124` |
| [Package derivative report](../../build/ui-face-captures/full/capture-sequence-20260904-173751/package-derivative-report.json) | Shared payload digest `8599f4a3b496c3e27a68279e4e134d8a9d7d2d90678ab6971f5d3cb5e2e3cb37` |

The [evidence archive](../../build/ui-face-captures/full/anki-garden-ui-faces-20260904-173751.zip) preserves the raw captures, assembled evidence, contact sheets, logs, reports, and a copy of the production candidate. The capture derivative remains a separate file. Archive identity and integrity results are recorded in the [capture report](../../build/ui-face-captures/full/capture-sequence-20260904-173751/capture-report.json). The [assembled manifest](../../build/ui-face-captures/full/capture-sequence-20260904-173751/assembled/manifest.json) is the authoritative surface inventory.

| Contact sheet | Surfaces |
| --- | ---: |
| [First run and Garden](../../build/ui-face-captures/full/contact-sheets/anki-garden-ui-contact-sheet-2.2.0-20260904-173751/01-first-run-garden.png) | 10 |
| [Collection](../../build/ui-face-captures/full/contact-sheets/anki-garden-ui-contact-sheet-2.2.0-20260904-173751/02-collection.png) | 6 |
| [Shop](../../build/ui-face-captures/full/contact-sheets/anki-garden-ui-contact-sheet-2.2.0-20260904-173751/03-shop.png) | 7 |
| [Progress and Settings](../../build/ui-face-captures/full/contact-sheets/anki-garden-ui-contact-sheet-2.2.0-20260904-173751/04-progress-and-settings.png) | 6 |
| [Anki and rewards](../../build/ui-face-captures/full/contact-sheets/anki-garden-ui-contact-sheet-2.2.0-20260904-173751/05-anki-and-rewards.png) | 7 |

The [contact-sheet index](../../build/ui-face-captures/full/contact-sheets/anki-garden-ui-contact-sheet-2.2.0-20260904-173751/contact-sheet-set.json) binds each tile to its source surface. Cream padding belongs to the contact-sheet presentation, not the captured add-on. Its pending-review label refers to human acceptance; the separate agent review above does not change `release_ready: false`.

The prior production archive and all historical captures remain preserved. This work does not publish, commit, merge, or approve the release.
