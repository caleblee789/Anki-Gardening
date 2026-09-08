# Typography, hierarchy, and terminology audit — 8 September 2026

Scope: all 53 surfaces in the six contact sheets, using the checked-in v29 capture contract. Existing work was committed to local main as `b0a44c1` before this implementation began.

Plant naming remains unchanged: **Bonsai Sprout**, **Full Bloom Bonsai**, and established purchasable item names retain their existing formatting.

## Shared corrections

- Use 20 px screen/dialog headings, 16 px section and product/card headings, 14 px body and effect descriptions, 13 px supporting copy and controls, and a 12 px minimum for metadata and badges. Keep emphasis on the title, state, meaningful numbers, and primary action.
- Aggregate reward counters use **Items & finds** consistently in Activity, Reviewer, session summaries, and sync summaries. Include independent item quantities and appearance unlocks; count each Find once without counting its inventory receipt again. Exclude purchases, uses, refunds, migrations, and adjustments. Garden Finds remains a valid heading only for the specific Find category.
- Upgrade saved Activity projections once, transactionally, preserving event identities, grouping, Coin/Growth amounts, and card counts. No reward rates or award rules change.
- Use **Shop**, **Coins**, **Plant in garden**, **Browse Shop**, **Plant beds**, and **Trophy room** consistently. Progress reads **X / Y Growth to Stage**; compact HUD progress uses the equivalent two-line hierarchy.
- Keep Appearance preview/equipment geometry stable between categories and preview states. Wrap effects, reserve control/feedback space, and show scrollbars only for actual overflow.
- Achievements use two readable columns; Settings distinguishes sections from control labels; Plant beds distinguishes completed requirements from remaining work; reward receipts distinguish planned values from committed results.

## Per-surface corrections

Numbers match the contact sheets, rather than legacy capture filenames. All 53 final surfaces have been validated and visually reviewed.

| # | Surface | Correction |
| --- | --- | --- |
| 01 | starter-deck-browser-home | Retain the compact Home entry, with readable supporting copy and one clear start action. |
| 02 | garden-starter-picker | Move the chooser toward the top; use a 20 px heading, 16 px plant names, and 13 px stage-preview captions. |
| 03 | garden-starter-selected | Keep selected-state emphasis on the chosen tile and the enabled continuation action. |
| 04 | garden-starter-placement | Use an explicit Plant in Bed N action and a readable two-line placement banner. |
| 05 | workspace-starter-awaiting-nurture | Place first-nurture guidance in the inspector and remove the competing onboarding prompt in the bottom strip. |
| 06 | workspace-welcome-settled | Use the shorter welcome heading, readable reward values, and one primary continuation action. |
| 07 | workspace-welcome-rewards-expanded | Separate Welcome gift from Past study rewards; keep granted item names intact. |
| 08 | garden-overview | Keep the garden unobstructed and the bottom plant identity and progress readable. |
| 09 | garden-inspector-nurtured | Use a 16 px full plant name, regular progress text, and an explicit More-menu indicator. |
| 10 | garden-inspector-available | Keep the same inspector hierarchy with Nurture as the primary action. |
| 11 | garden-move-plant | Separate move instructions from their title and keep the destination action unambiguous. |
| 12 | workspace-decoration-inspector | Use a 16 px decoration name and wrapping 14 px effect text in the anchored inspector. |
| 13 | collection-plants-page | Keep full plant names; distinguish the selected plant, location, stage progress, and history. |
| 14 | collection-species-details | Use the same readable details and stage-card hierarchy as Collection Plants. |
| 15 | collection-plant-details | Use Plant in garden for stored plants and preserve established plant/item names. |
| 16 | workspace-collection-plant-menu | Add an explicit More-menu indicator and retain readable menu actions. |
| 17 | workspace-collection-storage-confirmation | Use a 20 px confirmation title with a compact body and clearly separated actions. |
| 18 | collection-scenery-page | Use one wrapping catalog and a stable preview/equipment column. |
| 19 | workspace-scenery-preview | Reserve preview controls and feedback space so choosing a preview does not shift the scene. |
| 20 | workspace-scenery-applied-undo | Keep result feedback and Undo beside the preview; preserve equipment geometry. |
| 21 | collection-decorations-page | Use the same list/preview structure as Scenery and wrap long effects. |
| 22 | shop-plants-page | Use 16 px item names and quieter View growth stages actions. |
| 23 | shop-scenery-page | Use readable item names, effect descriptions, and consistent ownership/action labels. |
| 24 | shop-decorations-page | Apply the same hierarchy and allow long effect descriptions to wrap. |
| 25 | shop-supplies-page | Separate product name, benefit, duration, ownership, price, and action; show shared eligibility once. |
| 26 | workspace-shop-supplies-scroll-end | Keep final supply rows reachable, with unchanged product names and readable conditions. |
| 27 | shop-fertilizer-confirmation | Keep immediate benefit, duration, target, price, and queued-use timing distinct. |
| 28 | purchase-confirmation-growth-charge | Label Charges owned explicitly and retain exact before/after counts. |
| 29 | shop-purchase-receipt | Use an item-purchased heading with a separate destination and follow-up actions. |
| 30 | garden-use-fertilizer | Separate active fertilizer, queued-use guidance, and available stock. |
| 31 | garden-use-growth-charges | Use a shared Growth Charge eligibility note and preserve entry focus on that category. |
| 32 | growth-charge-use-ready | Label Charges remaining, After use, and Stage reward after use; preserve exact transaction values. |
| 33 | growth-charge-success-stage-reward | Use current receipt values and Stage reward earned after successful use. |
| 34 | progress-today-page | Use readable Activity metrics and the shared Items & finds total, including the inline session totals. |
| 35 | progress-today-details | Use 16 px Study rewards headings and regular 14 px requirements/values. |
| 36 | progress-achievements-page | Use two columns, concise objectives, readable reward rows, and one shared permanent-streak explanation. |
| 37 | workspace-achievements-scroll-end | Keep completion dates secondary and the final achievements reachable. |
| 38 | workspace-trophy-room | Prioritize trophy name, state, permanent bonus, requirement, and progress; put extra mechanics in Details. |
| 39 | progress-coins-page | Use the same Activity terminology and hierarchy for Coin-related navigation. |
| 40 | garden-settings | Separate 20 px dialog title, 16 px sections, 14 px control labels, and 13 px help. |
| 41 | workspace-settings-unsaved | Place unsaved feedback beside Save and keep the action footer pinned. |
| 42 | garden-diagnostics | Group Support with Artwork check and give the diagnostic result its own heading. |
| 43 | workspace-diagnostics-warning-details | Keep technical details in a bounded scroll area with readable monospace text. |
| 44 | active-deck-browser-home-after-nurture | Make the existing full plant name prominent on Home and use canonical Growth to Stage progress. |
| 45 | reviewer-hud-expanded | Preserve Bonsai Sprout formatting; enlarge small status copy and stack active consumable rows. |
| 46 | workspace-reviewer-collapsed | Keep the collapsed control compact with a descriptive plant/progress tooltip. |
| 47 | reviewer-reward-dock-bundle | Use readable reward titles and avoid repeating milestone badges already present in the title. |
| 48 | workspace-reviewer-rewards-list | Use readable reward history rows and the shared Items & finds counter. |
| 49 | session-summary-after-review | Put cards studied before the metrics and indent Shared Growth beneath To plants. |
| 50 | sync-rewards-summary | Match session-summary typography and counter meaning; avoid duplicate Full Bloom badges. |
| 51 | progress-plant-beds-starting | Use 20 px page/16 px card headings, complete requirements, and clear next-unlock guidance. |
| 52 | progress-plant-beds-partial | Show stage-qualified species progress and the remaining requirement for the next unlock. |
| 53 | progress-plant-beds-unlocked | Use All 6 beds unlocked, completed-requirement wording, secondary dates, and received reward copy. |

## Verification

Targeted existing regression checks cover reward counting and projection migration/rollback/restart, summaries, Reviewer HUD, formatting, interaction contracts, and the independent capture validator. Existing Qt-dependent tests that cannot run in the repository venv are supplemented by native Anki capture checks.

Final result: **53 of 53 surfaces captured fresh, zero text-layout warnings, six valid contact sheets, and no unresolved issues found in the reviewed states.** The independent validator returned valid for the manifest and all six sheets. All 53 raw screenshots were visually reviewed directly or verified byte-identical to a screenshot visually inspected during this task; the per-surface record identifies which.

The final capture ran in native Anki 26.8.1 on the primary display at 100% scale, in a fresh sync-disabled disposable profile. The isolated process exited gracefully with code 0. Normal Anki was not modified. Supplementary native checks cover Appearance text and category switching at 1280 × 800, 1040 × 720, and 860 × 580; minimum-size Achievements and Plant beds; supply transactions; Reviewer feedback; settings; and the established capture contracts.

Issues found in intermediate captures were fixed and recaptured: the missing purchase-receipt title, first-nurture guidance and competing prompt, detached decoration anchor, redundant supply heading, excess discovery-count emphasis, stale Appearance row heights and scrollbar shift, and stale Achievement category and scroll heights. The final Achievement check leaves only normal bottom padding (last row at y=409 in a 426 px viewport).

The remaining generated advisory concerns identical Collection Plants and Species screenshots. Both historical routes intentionally open the same selected Bonsai in the unified Collection panel. This was inspected and documented; no product correction is needed. Generated reports and sheets retain their original review-required release status. The separate Codex review records completion of this task without claiming formal release approval.

- Version: 2.2.0
- Production archive: [anki_garden.ankiaddon](</Users/test/Documents/Anki Gardening.nosync/dist/anki_garden.ankiaddon>)
- Production SHA-256: `41494138a027f3f1ea211c467bb967249b8907958ab5f24e9784e9effe7bfa8b`
- Capture derivative SHA-256: `4df6560048082cf1e4b3578e6906cbf11066f5e70560319ce0a85f2a5e95ae45`
- Evidence archive SHA-256: `f8b0fe88f25919fcaf338a887830666f48e9a88b41335323144e12c9834e656b`
- All 266 shared production/capture entries are byte-identical. All 24 modified runtime Python files match the production archive. Both add-on archives passed ZIP CRC verification.

- [Raw manifest](</Users/test/Documents/Anki Gardening.nosync/build/ui-face-captures/full/capture-sequence-20260908-012834/assembled/manifest.json>)
- [Capture report](</Users/test/Documents/Anki Gardening.nosync/build/ui-face-captures/full/capture-sequence-20260908-012834/capture-report.json>)
- [Independent validation](</Users/test/Documents/Anki Gardening.nosync/build/ui-face-captures/full/capture-sequence-20260908-012834/independent-validation.json>)
- [Codex visual review, all 53 surfaces](</Users/test/Documents/Anki Gardening.nosync/build/ui-face-captures/full/capture-sequence-20260908-012834/codex-visual-review.json>)
- [Evidence archive](</Users/test/Documents/Anki Gardening.nosync/build/ui-face-captures/full/anki-garden-ui-faces-20260908-012834.zip>)
- [Contact-sheet index](</Users/test/Documents/Anki Gardening.nosync/build/ui-face-captures/full/contact-sheets/anki-garden-ui-contact-sheet-2.2.0-20260908-012834/contact-sheet-set.json>)

