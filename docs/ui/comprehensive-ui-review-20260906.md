# Anki Garden UI review — September 6, 2026

This review covers the 50 active v29 surfaces across Garden and onboarding,
Collection and Appearance, Shop and item use, Progress and Settings, and Anki
study/reward integration. The supplied five contact sheets were compared with
the original full-resolution captures and the current source. Normal 100% UI
scale is the primary acceptance target.

## Findings and implementation

| Area | Finding | Correction |
| --- | --- | --- |
| Color | Muted text fell below 4.5:1 on hover and raised Shop surfaces. | Brightened the shared muted token; checked primary, secondary, and muted text across the actual surface palette. |
| Controls | Fixed button heights could clip text; previous label widths could leave excess space. | Actions use measured text, icons, and padding while retaining their compact default height. |
| Garden | A constrained plant popover acquired horizontal overflow when its vertical scrollbar appeared. | Removed unnecessary platform button width floors while preserving complete action labels and the normal single-row layout. |
| Collection | Repeated stage labels and oversized cards reduced the number of plants visible. | Reduced card height and thumbnail canvas; show the stage directly beneath each species. |
| Collection details | The split layout used a fixed breakpoint independent of content; the Growth label was constrained to a small right-aligned box. | Use measured gallery/detail widths, give Growth the available row width, and retain the compact detail dialog route. |
| Collection appearance | A summary path referenced an uninitialized container. | Construct the summary and its layout before adding appearance facts. |
| Progress | Garden Find totals repeated their label; completion-bonus copy was awkward. | Show the count once and use “Bonus every 5 completions.” |
| Progress | Fixed summary columns could collide when space was constrained. | Totals reflow when their actual content cannot fit. |
| Coins | The empty state repeated the section context. | Use “No activity yet” and “Coins you earn and spend will appear here.” |
| Welcome and trophies | Wrapped content could lose its last line or retain excessive height after widening; welcome reward scrolling was suppressed by its parent. | Release stale height measurements before fitting each label, preserve the local reward scroll area, and fit header/actions to their content. |
| Settings | Changing a switch replaced its explanatory accessible description with its state alone. | Preserve the explanation and append the current state. |
| Anki Home | Fixed-height overlays and buttons could overlap notices or suppress useful progress on narrow windows. | Use normal document flow, preserve progress, and fit actions to their labels. |
| Study and rewards | Reward titles and metric captions depended on fixed dimensions. | Fit the shared receipt header, footer, and metric row to their actual content. Normal reviewer totals remain three columns. |
| Plant artwork | Sunflower Seed and Sprout used canvas-center metadata despite off-center silhouettes. | Corrected their optical centers in both the runtime manifest and authoring calibration. |
| Small plant icons | A 16px minimum inner canvas could paint foliage against an icon edge. | Preserve a physical transparent pixel around the complete silhouette. |
| Documentation | The surface inventory still counted a retired Appearance panel. | Reconciled it with the 50 active surfaces and current navigation. |

The existing hand-painted assets, stage progression, plant positions, scenery
lighting adjustments, soil contact, and shadow treatment were reviewed together.
The earlier continuous-background work is retained, including the unchanged
Home banners. The UI changes do not alter rewards, progression, inventory,
scheduling, or sync behavior.

## Visual and interaction review

The review checks complete text, title hierarchy, consistent action priority,
spacing, artwork crop/optical scale, soil contact, foreground contrast, empty
states, preview/equipped states, purchase/use confirmations and matching receipts.
Sparse pages retain natural content height; cards are not stretched merely to
fill a persistent workspace window.

Core language remains consistent: **Nurture** changes the plant receiving
Growth; viewing or moving another plant does not. Previewing scenery does not
save it; **Equip** commits it and **Undo** restores the previous choice. Owned
supplies, purchase costs, queued effects, projected Growth, and committed results
continue to use the existing engine projections.

## Contact sheets

1. [Garden and onboarding](../images/ui-review-20260906/01-garden-and-onboarding.png) — 12 surfaces.
2. [Collection and appearance](../images/ui-review-20260906/02-collection-and-appearance.png) — 9 surfaces.
3. [Shop and item use](../images/ui-review-20260906/03-shop-and-item-use.png) — 12 surfaces.
4. [Progress and settings](../images/ui-review-20260906/04-progress-and-settings.png) — 10 surfaces.
5. [Anki integration and rewards](../images/ui-review-20260906/05-anki-integration-and-rewards.png) — 7 surfaces.

These checked-in PNGs are byte-identical copies of the final generated sheets.
Their cream padding is outside the captured UI. Raw PNGs were reviewed at full
resolution; the sheets provide the overview. Scroll-boundary rows intentionally
show partially visible content that is reachable by scrolling.

## Verification record

**Completed:** the final 22-surface representative preflight and assembled
50-surface full native capture pass the independent validators. All 50 raw
surfaces and five sheets were visually inspected by Codex, with no remaining
observed UI defects. The full evidence has zero capture, text-layout, and geometry
errors. Its one non-blocking duplicate-image advisory covers **Collection plants**
and **Species details**: both routes intentionally use the same selected-plant
panel. Their separate contract labels remain in the inventory.

Capture used Anki 26.8.1 on macOS, primary Built-in Retina Display, **100% UI/font
scale and 2× device pixels**, in fresh sync-disabled profiles. The final process
and clean-shutdown gates passed. Native full-capture interaction checks include
scroll reachability, settings draft behavior, scenery preview/equip/undo,
matching equipment descriptions, purchase/use results, and retained nurtured
plant identity. Technical support details remain inside their explicit
Settings disclosure.

The production suite passed **2,494 tests**, with **55 environment-dependent
skips and one deselected annual simulation parity gate**. After the final native
layout fixes, affected existing tests passed again: 24 portable checks, seven
native Qt checks, and 15 capture acceptance checks. Existing tests were extended
or simplified; no new test files were introduced. The separate full annual
66-scenario replay was not repeated for this presentation pass.

Native review caught and resolved the plant inspector action overflow,
constrained Collection Growth text, suppressed welcome scrolling, and stale
wrapped-label heights. A capture-only repair now waits for queued Qt font and
content measurements before comparing Growth Charge preview/result geometry;
it retains the same footer anchoring checks and does not change production code.
The final repair captured the two affected charge views and reused 48 exact
compatible images from this review, with verified immutable lineage.

The immutable evidence root is `build/ui-comprehensive-20260906-084903/`.
The [local handoff index](../../build/ui-comprehensive-20260906-084903/CONTACT-SHEETS.md)
links all raw PNGs through the manifest, the capture report, ZIP archive,
package parity, and the separate per-image Codex visual-review ledger. These
large native evidence files remain local; the five sheets above are checked in.

| Artifact | SHA-256 |
| --- | --- |
| Production add-on, 104,361,845 bytes / 259 entries | `43639b9a539a98d4630aa637451bc500a5276d20638f1348d44c97b351556a6d` |
| Capture derivative | `af00142e2cd285d323849be1eae99c0cd641e0032441c316bcf158c5b4821354` |
| Native capture ZIP | `424d0d9baa5baab631224c5cf77e824d49d730e0878b5015ab0804a8c1e3b5e1` |

All 258 shared payload entries match byte for byte. The production archive is
99.53 MiB, below the existing 100 MiB limit. Capture helpers are excluded from
production. The root deliverable matches the frozen reviewed package.

The sheets retain their generation-time “visual review pending” caption.
The subsequent Codex review is recorded separately to preserve the original
PNG hashes; this does not imply human release approval.

Artwork checks cover all 60 source images, 720 rendered thumbnails, and 9,720
placements across all nine sceneries. No crop, off-canvas alpha, or placement
warnings remained. Existing tests cover keyboard actions, switch descriptions,
responsive dialogs, scroll containment, and shared color contrast. The bounded
larger-text checks already completed are supplemental; 100% presentation is the
primary review target.

The [previously recorded progression pacing hold](combined-integration-20260906.md) remains outside this UI pass.
This document does not grant public release approval or claim cross-platform
native acceptance.
