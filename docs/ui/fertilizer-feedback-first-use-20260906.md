# Fertilizer feedback and first-use Shop candidate

Implementation is complete for the identified UI defects and Shop construction work. Native Anki verification is **paused at the user's request**. The desktop-switch fix, visible toast timing, and complete navigation performance targets have not received native acceptance.

## Changes

- Removed the unused `FertilizerStatusBlock` from the selected-plant card. Refreshing active fertilizer can no longer reveal that unlaid-out widget over the heading. The compact fertilizer name and remaining-card row stays in place.
- Removed checkpoint text, its tooltip, and accessibility copy from that card. Stage Growth remains visible; checkpoint mechanics and rewards are unchanged.
- Fertilizer success displays for 1,500 ms and fades over 250 ms. Reduced motion hides it after 1,750 ms without animation. Replacement, dismissal, and destruction cancel the previous lifecycle and reset opacity. Other success, error, and actionable notification policies remain unchanged.
- Parented Shop product-description labels before their first visibility change. Catalog insertion now performs one grid layout pass per batch.
- Shop creates its shell on demand and populates only the requested catalog. Target plant and catalog selection are set before population. Clean pages retain their controls; committed changes invalidate data and rebuild only the visible page. Plant supplies reuses the lightweight helper without loading the Shop catalogs.
- Added `shop.catalog.<index>` spans to the existing performance recorder.

Only `ankigarden/ui/dashboard.py` differs in the frozen candidate's runtime Python payload from baseline commit `2288010f5989454983b02601f867c86edf5b38d3`. The existing popover/navigation tests were extended and one small shared-toast lifecycle test was added. Fertilizer effects, inventory rules, Growth, rewards, and save formats are unchanged in this candidate.

## Frozen candidate

Archive: `build/fertilizer-feedback-first-use-20260906/anki-garden-feedback-candidate-v2.ankiaddon`

SHA-256: `ae0ef623325fe9dbb10a61e304f3cdd72b2a53dfe35c4c9b15915456c164e124`

Size: 104,362,610 bytes; 259 entries. The builder validated every entry against the frozen source, including the canonical runtime asset manifest and production capability module. ZIP integrity also passed.

The shared working tree received other edits during verification. Those edits were preserved and are not included in this frozen candidate. Use the named archive and its evidence, rather than assuming the current working tree or `dist` still represents this candidate. Nothing was published or installed in the normal Anki profile.

## Offline evidence

All evidence below is in `build/fertilizer-feedback-first-use-20260906/`.

| Check | Result | Evidence |
| --- | --- | --- |
| Interaction, navigation, transactions, helpers, economy, package, performance contracts | 198 passed | `offline-tests.log` |
| Focused source Qt regression suite, offscreen | 29 passed, 1 skipped | `live-qt-tests.log` |
| Same focused suite against frozen production candidate v2, offscreen | 28 passed, 2 skipped | `frozen-candidate-v2-qt-tests.log` |
| Candidate entry integrity and source parity | Passed | `package-v2.json`, `frozen-candidate-v2-verification.json` |
| Whitespace and Python syntax | Passed | Source checks |

The two production-package skips import capture-only modules, which production intentionally omits. The generic skip messages in those existing tests describe the runtime as unavailable; the remaining 28 checks did use Anki's Qt runtime. An optional broader component-gallery run failed an unrelated compact-button height assertion (30 px versus the expected 32 px). That assertion was not changed or counted as passing.

The focused checks cover inactive/active fertilizer, repeated refresh, reopening the card, plant selection, preserved Growth state, lazy catalog creation, target selection, clean-page reuse, invalidation, toast expiry/replacement/dismissal, reduced motion, and destruction with pending feedback. They do not prove macOS Space behavior or visible animation quality.

## Shop construction probe

These are separate-process **offscreen Qt operation timings**, not native click-to-usable measurements. Baseline and candidate used the same fixture. The v2 feedback-only adjustment does not change this catalog path.

| Operation | Baseline | Candidate |
| --- | ---: | ---: |
| Shell construction plus first Plants population | 542.4 ms | 198.0 ms |
| Shell construction | 517.9 ms | 74.1 ms |
| First Supplies population | Already built during construction | 76.0 ms |
| First Scenery population | Already built during construction | 214.5 ms |
| First Decorations population | Already built during construction | 48.3 ms |
| Repeated catalog visits | 1.7–2.4 ms | 1.9–3.5 ms |
| Unexpected parentless label Show events | 14 | 0 |

Raw results and stacks: `baseline-catalog-probe.json`, `candidate-catalog-probe.json`; reproduction helper: `catalog_probe.py`. Other first-use work across Garden, Collection, Progress, Settings, and Plant supplies still requires measurement in the resumed native run.

## Native pause and resume

One disposable, sync-disabled profile was verified and opened to Garden with Anki full-screen. Testing stopped **before the first Shop click**. No completed first-Shop trial, fertilizer sequence, or refreshed capture set exists for this change.

The preserved session used candidate v1 (`e46827c9ed6efc23f71271b34d5528d49607b6dfa2be8228b717595d0712d7d5`). Candidate v2 narrows the deferred success notification to fertilizer and clears it after a later failed action. It was packaged after the pause and was not installed into the live session.

When the user requests resumption:

1. Recheck the isolated-session process, window, filesystem, and sync gates. Use fresh profiles with the exact v2 archive for acceptance; do not treat the preserved v1 session as v2 evidence.
2. Run the first Shop click across three fresh full-screen launches. Require no Space change or unexpected parentless-window event; then check repeated navigation and windowed operation.
3. Record first-use and repeated click-to-usable timings for Garden, Collection, Shop, Progress, Settings, and Plant supplies. Targets remain under 500 ms initially and under 100 ms on repeat visits. Investigate measured misses without moving the work into startup.
4. Verify fertilizer success at display, hold, fade, and hidden states, including reduced motion and replacement. Inspect card refresh, switching plants, and reopening.
5. Refresh the affected Garden and Shop captures and inspect the timed sequence. Keep historical evidence intact.

Local process/base details and incomplete-observation labels are in `build/fertilizer-feedback-first-use-20260906/RESUME.md`. Publication remains outside scope.
