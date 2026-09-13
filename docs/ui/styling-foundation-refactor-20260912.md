# Shared styling refactor validation — September 12, 2026

The refactor extends the existing theme foundation without changing rendered styles or interaction code. The baseline includes the pre-existing uncommitted reviewer, reward, engine, and storage work. See the [development guide](../development.md#shared-ui-styling) for the shared-definition/consumer map and intentional variants.

## Implementation boundary

- Exactly five production archive entries changed: `ui/theme.py`, `ui/dashboard.py`, `ui/home_widget.py`, `ui/garden_studio.py`, and `ui/decoration_card.py`. The other 267 entries, including all artwork, reviewer/reward code, persistence, and gameplay modules, are byte-identical to baseline.
- All existing palette, typography, spacing, radius, button-size, and control-geometry values were preserved. The migrated UI methods are structurally unchanged after excluding stylesheet arguments; Home rendering functions and classes are unchanged.
- Existing control generators and Home CSS produce byte-identical strings. Evaluated local style declarations are equivalent; only insignificant stylesheet whitespace differs. The eight migrated interaction-state colors now have one literal definition each in the theme module.
- Four small cases extend the existing foundation test file. No widget reconstruction, new signal connections, state transitions, application-wide styling, version change, or data migration was introduced.

## Automated and runtime evidence

| Check | Baseline | Candidate |
| --- | --- | --- |
| Default suite, excluding the unrelated annual economy simulation | 1,794 passed; 21 skipped; 2 existing failures | 1,798 passed; 21 skipped; same 2 failures |
| Complete release-evidence lane with Anki Qt libraries | 849 passed; 1 skipped | 849 passed; same skip |
| Focused Qt interaction/layout checks | 52 passed; 2 skipped | 52 passed; same skips |
| Native v29 preflight/full capture | 23 / 53 surfaces; valid | 23 / 53 surfaces; valid |
| Supplementary push-button/tool-button state images | 16 images | All 16 pixel-identical |
| Actual Qt appearance control clicks | Preview/Cancel: no saves or state changes; Equip/Undo: 2 applies and 2 saves total | Identical results; original equipment restored |

Both native capture runs used fresh, separately keyed, sync-disabled Anki 26.8.1 profiles on macOS, the primary display, and `QT_SCALE_FACTOR=1.0`. All 53 paired states have matching client dimensions, device-pixel ratio, capture environment, and scenario identity. The final capture validators, package/derivative checks, geometry/text checks, memory/shutdown gates, asset audit, bytecode compilation, ZIP integrity, and `git diff --check` passed. Each full run contains six contact sheets.

The supplementary Qt checks use Anki's installed Qt libraries with the offscreen platform. They cover mouse/keyboard activation, disabled controls, preview/Cancel, Equip/Undo, purchase receipts, navigation, HUD dragging and collapse/expansion, reward sequencing with motion enabled/disabled, and dialog layouts. The appearance probe reuses the existing in-memory storage fixture and checks its save counter; it is not a durable-storage or live-sync test. Native captures separately cover the running Anki UI, item-use receipts, session summaries, and sync-summary presentation.

## Pixel comparison

48 of 53 full native images are pixel-identical. The remaining five differ only in these capture-time fields; every other pixel matches. Each changed region was inspected against both originals. No expected image or production clock was modified.

| Surface | Baseline → candidate timestamp |
| --- | --- |
| Today | 10:21 PM → 10:39 PM |
| Today details | 10:26 PM → 10:44 PM |
| Coins | 10:26 PM → 10:44 PM |
| Diagnostics | 10:27 PM → 10:45 PM |
| Expanded diagnostic warning | 10:27 PM → 10:45 PM, in the last-check label and support-report text |

[Full pixel comparison](../../build/ui-foundation-refactor-20260912-221557/pixel-comparison-full.json) · [Control-state comparison](../../build/ui-foundation-refactor-20260912-221557/pixel-comparison-controls.json) · [Evaluated stylesheet comparison](../../build/ui-foundation-refactor-20260912-221557/style-equivalence.json) · [Behavior/source preservation checks](../../build/ui-foundation-refactor-20260912-221557/behavior-preservation.json)

## Retained issues and limits

- `test_runtime_timing_finishes_for_early_reviewer_and_maintenance_failures` fails because its existing recorder stub lacks `answer_stage`. It fails identically before and after.
- `test_release_notes_preserve_review_required_boundary` expects wording absent from the existing release notes. It fails identically before and after.
- One legacy dialog-scroll test imports `_UiFaceCaptureRunner` from the compatibility bootstrap, which now exports only `start_capture`; the test skips on both archives. Its legacy assertions remain unverified. The current v29 native capture and other scroll/layout checks passed.
- Supplementary Qt runs emit the same existing missing-font-alias and `CollectionCatalogTile` maximum-size warnings on both archives. No corresponding new visual defect was observed.
- The initial sandboxed Anki launch could not access macOS display services. A GUI-authorized retry completed in a fresh disposable profile. Initial full-lane Qt collection errors were resolved using a task-local Python 3.13 Pillow wheel matching the existing 11.3.0 version, plus access to the unchanged capture test helpers. An initial appearance probe retained a deleted tile after Cancel; resolving the current tile fixed the probe. These were harness/environment issues, with original logs retained.
- Cross-platform, live AnkiWeb sync, and public-release acceptance were not part of this refactor. Capture reports retain `quality_status: review-required` and `release_ready: false`; automated parity is not human release approval.

## Immutable artifacts

Artifacts live under `build/ui-foundation-refactor-20260912-221557/`. Baseline source hashes, the original dirty-tree patch, the prior distribution archive, logs, raw captures, and comparison crops are retained.

| Package | SHA-256 |
| --- | --- |
| [Baseline production archive](../../build/ui-foundation-refactor-20260912-221557/baseline/baseline.ankiaddon) | `92d4dbab59f6f3e6430619b1f98814f23307ab198858879534dadeaaa4b96ce4` |
| [Candidate production archive](../../build/ui-foundation-refactor-20260912-221557/candidate/candidate.ankiaddon) | `3209a7f4ef4ec5949f9fd1ed16419a550fb92017afb49618c2f59dbd3123e6ed` |
| Baseline capture derivative | `272c7cd6f9f5fdf12f886ec7a9f71d56a69fce357014a338dd453c9473f9b88e` |
| Candidate capture derivative | `7dd3a3a8ff20276b5ec5082282e89efda8561f9058086c48f257272a7df3a020` |

Package version remains 2.2.0. The candidate production archive is also copied to `dist/anki_garden.ankiaddon`; no publication was performed.

Baseline: [report](../../build/ui-foundation-refactor-20260912-221557/baseline/captures/full/capture-sequence-20260912-222421/capture-report.json) · [manifest](../../build/ui-foundation-refactor-20260912-221557/baseline/captures/full/capture-sequence-20260912-222421/assembled/manifest.json) · [capture archive](../../build/ui-foundation-refactor-20260912-221557/baseline/captures/full/anki-garden-ui-faces-20260912-222421.zip) · [contact-sheet index](../../build/ui-foundation-refactor-20260912-221557/baseline/captures/full/contact-sheets/anki-garden-ui-contact-sheet-2.2.0-20260912-222421/contact-sheet-set.json)

- [1 — garden and onboarding](../../build/ui-foundation-refactor-20260912-221557/baseline/captures/full/contact-sheets/anki-garden-ui-contact-sheet-2.2.0-20260912-222421/01-garden-and-onboarding.png)
- [2 — collection and appearance](../../build/ui-foundation-refactor-20260912-221557/baseline/captures/full/contact-sheets/anki-garden-ui-contact-sheet-2.2.0-20260912-222421/02-collection-and-appearance.png)
- [3 — shop and item use](../../build/ui-foundation-refactor-20260912-221557/baseline/captures/full/contact-sheets/anki-garden-ui-contact-sheet-2.2.0-20260912-222421/03-shop-and-item-use.png)
- [4 — progress and settings](../../build/ui-foundation-refactor-20260912-221557/baseline/captures/full/contact-sheets/anki-garden-ui-contact-sheet-2.2.0-20260912-222421/04-progress-and-settings.png)
- [5 — anki integration and rewards](../../build/ui-foundation-refactor-20260912-221557/baseline/captures/full/contact-sheets/anki-garden-ui-contact-sheet-2.2.0-20260912-222421/05-anki-integration-and-rewards.png)
- [6 — plant beds](../../build/ui-foundation-refactor-20260912-221557/baseline/captures/full/contact-sheets/anki-garden-ui-contact-sheet-2.2.0-20260912-222421/06-plant-beds.png)

Candidate: [report](../../build/ui-foundation-refactor-20260912-221557/candidate/captures/full/capture-sequence-20260912-224206/capture-report.json) · [manifest](../../build/ui-foundation-refactor-20260912-221557/candidate/captures/full/capture-sequence-20260912-224206/assembled/manifest.json) · [capture archive](../../build/ui-foundation-refactor-20260912-221557/candidate/captures/full/anki-garden-ui-faces-20260912-224206.zip) · [contact-sheet index](../../build/ui-foundation-refactor-20260912-221557/candidate/captures/full/contact-sheets/anki-garden-ui-contact-sheet-2.2.0-20260912-224206/contact-sheet-set.json)

- [1 — garden and onboarding](../../build/ui-foundation-refactor-20260912-221557/candidate/captures/full/contact-sheets/anki-garden-ui-contact-sheet-2.2.0-20260912-224206/01-garden-and-onboarding.png)
- [2 — collection and appearance](../../build/ui-foundation-refactor-20260912-221557/candidate/captures/full/contact-sheets/anki-garden-ui-contact-sheet-2.2.0-20260912-224206/02-collection-and-appearance.png)
- [3 — shop and item use](../../build/ui-foundation-refactor-20260912-221557/candidate/captures/full/contact-sheets/anki-garden-ui-contact-sheet-2.2.0-20260912-224206/03-shop-and-item-use.png)
- [4 — progress and settings](../../build/ui-foundation-refactor-20260912-221557/candidate/captures/full/contact-sheets/anki-garden-ui-contact-sheet-2.2.0-20260912-224206/04-progress-and-settings.png)
- [5 — anki integration and rewards](../../build/ui-foundation-refactor-20260912-221557/candidate/captures/full/contact-sheets/anki-garden-ui-contact-sheet-2.2.0-20260912-224206/05-anki-integration-and-rewards.png)
- [6 — plant beds](../../build/ui-foundation-refactor-20260912-221557/candidate/captures/full/contact-sheets/anki-garden-ui-contact-sheet-2.2.0-20260912-224206/06-plant-beds.png)
