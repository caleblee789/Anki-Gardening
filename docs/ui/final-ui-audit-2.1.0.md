# Anki Garden 2.1.0 Final UI Audit

Status: current automated and macOS Qt capture record for Release 2.1.0.
Capture contract v19 completed at 126/126 distinct ordered surfaces, each once
at canonical 100% scale, in 17 manifest-owned contact sheets. The final run is
`build/ui-face-captures/capture-sequence-20260823-000843`; it is fail-closed,
warning-free, `quality_status: clean`, and validator `valid`. Resize,
breakpoint, 150%, and 200% screenshot duplicates are excluded while responsive
geometry remains an automated release gate. Historical v8 evidence below is
retained only for its audited 2026-08-15 source. Native Windows/Linux GUI,
screen-reader, human/device, restart, and strict end-to-end live acceptance
remain separate and unrun.

## Current v19 outcome

The current 126-face set covers the final Growth, reward, achievement, Garden
Find, Reviewer feedback, transaction, onboarding, Collection, Nursery, Garden,
Progress, Settings, loading, empty, stale, warning, error, success, keyboard,
and reduced-motion surfaces. The preceding sheet audit found and drove fixes
for SVG weather previews, Dashboard popover/placement framing, missed-streak
projection, Collection empty-state timing, onboarding completion copy, and
Collection mechanics controls. The final corrected faces 092, 117, and 119
were inspected at native screenshot resolution; a redundant full-set re-audit
was skipped at user direction.

## Historical v8 outcome

The candidate preserves the approved Verdant Twilight V6 identity, six-bed scene geometry, plant placement, interactions, saved-state behavior, and learner-facing feature set. The final review found two remaining product-UI defects and one evidence-gate defect; all three were repaired:

1. Home screenshots could capture the macOS wallpaper and still pass a generic color audit. Home capture now prefers the foreground window, can composite the Qt shell with the WebEngine surface, and requires semantic Garden mint/dark-shell evidence.
2. The compact Customize Garden Effects view compressed its advanced copy into an unreadable column and did not clearly distinguish previewing from saving. It now uses a stable vertical block with `Included appearance`, explicit draft/save guidance, and the action `Preview included appearance`.
3. The first-run statistics/header card was taller and emptier than its content required. Its guided-state minimum heights now compact responsively while normal dashboard density remains unchanged.

No other then-current surface showed a release-blocking display, wording,
repetition, control, asset, preview, focus, clipping, or responsive defect after
the repairs. The audited macOS candidate therefore had no known remaining UI
defect within that historical contract.

## Complete review scope

| Area | What was assessed | Final disposition |
|---|---|---|
| First run and Home | Deck Browser and Overview previews, starter state, setup guidance, action hierarchy, image readiness, and Home open behavior | Clean after semantic Home-capture repair; production DOM and screenshots verified |
| Garden | Header, statistics, six-bed scene, plant cards, selection, nurturing, fertilizer, move mode, story, long names, occupied plots, and missing-art fallback | Clean; V6 geometry and interaction contracts preserved |
| Garden Progress | Growth, streak, Coins, achievements, committed reward history, Garden Finds, Collection, empty states, and stress states | Clean; no remaining redundant or competing hierarchy found |
| Nursery and purchases | Plants, consumables, Garden spaces, Weather/Scenery, owned/locked/success states, long rows, and confirmation dialogs | Clean; controls remain reachable above stable footers |
| Settings and Customize | Tabs, toggles, text fields, preview cards, Effects, diagnostics, validation, unsaved changes, disabled states, and production-only controls | Clean after Effects repair; capture-only control absent from production |
| Buttons and controls | Primary/secondary hierarchy, enabled/disabled states, footer alignment, keyboard focus, touch-target sizing, close actions, and switch clarity | Clean; production Settings measured 46 px for the visible Cancel and Save actions, above the 44 px minimum |
| Tabs and drop-down behavior | Tab labels, active states, responsive widths, keyboard reachability, and selection ownership | Clean; the internal hidden combo box is intentionally not learner-facing and no visible drop-down needed adjustment |
| Copy and repetition | Titles, helper copy, stage/Growth language, purchase terms, action casing, empty/error states, and accessible descriptions | Clean; essential accessible context remains self-contained rather than being removed as visual repetition |
| Color and visual hierarchy | V6 dark-green shell, mint actions/focus, gold brand accent, disabled states, artwork legibility, overlays, and scene-to-panel balance | Clean across normal, focus, disabled, reduced-motion, and stress captures; identity was refined rather than redesigned |
| Responsive and accessibility | Canonical 100% captures plus automated minimum/default/large, breakpoint, 150%, and 200% geometry; keyboard focus, scroll reachability, and reduced motion | Automated geometry and capture warnings are clean; native screen-reader and human/device acceptance remain unrun |
| State and recovery | Unsaved changes, validation failure, missing artwork, save status, and production/capture separation | Clean in automated/capture evidence; final-SHA restart and persistence journeys remain unrun |

## Historical v8 assets and preview sizing

The manifest-owned runtime audit reports 86 assets: 9 backgrounds, 1 decoration, 60 plant stage images, 9 UI assets, and 7 Weather assets. The final review covered the dedicated Home crops, 4:3 and 16:9 scene variants, all six plant spaces, every represented plant stage, Nursery/Story previews, watering-can positions, transparent artwork bounds, and missing-art fallback.

No asset or plant-preview resize was justified for that historical candidate.
Its preview crops preserved every landmark and bed; plant art remained grounded
and readable without clipping or unintended upscaling. Its frozen production
archive was 81,702,743 bytes (77.92 MiB) with 262 files. Those counts and that
optimizer result are historical and are not promoted to the current package.

## Capture evidence

- Contract v19: 126 expected, 126 captured, requested Qt scale factor `1.0`,
  primary display, zero failures, zero text-layout warnings, quality `clean`.
- Manifest:
  `build/ui-face-captures/capture-sequence-20260823-000843/20260823-000847/manifest.json`.
- Contact-sheet set:
  `build/ui-face-captures/contact-sheets/anki-garden-ui-contact-sheet-2.1.0-20260823-000843`,
  17 pages and 126 surfaces, validator `valid`.
- Evidence ZIP:
  `build/ui-face-captures/anki-garden-ui-faces-20260823-000843.zip`.
- Production archive: 273 entries, 81,884,216 bytes, SHA-256
  `005cae6ee1278bcdc68756f6d36b9e3857c3babbec5124219e8eea9930189dc7`.
- Capture-derivative add-on SHA-256:
  `10e7760fb1dfa098acfaab018693fa3acb281c4bcdaccb9b401550b31a2d43ff`.
  This is the derivative `.ankiaddon` hash, not the evidence-ZIP hash.
- All 272 shared payloads are byte-identical, with shared-payload SHA-256
  `47eb2980055297b05753c9c8739dd110ba2c45260b20afbcef39151106d92a9d`.
  The only permitted differences are capture-only `capture_ui_faces.py` and
  mode-specific `build_capabilities.py`.
- The runner retained the newest three complete capture/contact-sheet sets and
  preserved partial diagnostic output, including the older explicitly named
  partial set.

Historical v8 evidence remains recorded in repository history: one 146/146
visual run and one fail-closed 139/146 exact-source run with seven omitted Home
frames. It is not current-source evidence.

The capture build is deliberately different from the production archive because only the capture build contains the fail-closed screenshot harness. The production package excludes `capture_ui_faces.py` and reports production capabilities only.

## Automated validation

- Full repository suite: 1,856 passed and 8 skipped.
- Package tests: 10 passed before the final UI/capture-only geometry fixes.
- Focused post-fix checks: 3 passed; Python compilation and
  `git diff --check` passed. The broad suite was intentionally not repeated for
  the final narrow geometry adjustment.
- Production/capture derivative parity: 272 shared entries byte-identical.
- Capture geometry, fixture postconditions, semantic Home checks, and
  contact-sheet validation: 126/126 faces, 17/17 sheets, zero failures, zero
  text-layout warnings, release validation `valid`.

## Exact-production macOS acceptance boundary

The current archive is `dist/anki_garden.ankiaddon`, SHA-256
`005cae6ee1278bcdc68756f6d36b9e3857c3babbec5124219e8eea9930189dc7`.

A disposable macOS Anki 26.8.1 startup/import smoke passed for the immediately
preceding production package before the final UI/capture-only fixes. It verified
unique process/window/filesystem identity, sync-disabled isolation, add-on hook
registration, production capabilities, and database integrity, then stopped
only the disposable process. Because the source and package hash changed after
that smoke, it is evidence for the launch/import path only. It is not final-SHA
runtime acceptance and did not cover complete journeys, restart, or persistence.
The final capture derivative did launch successfully with all 272 production-
shared payloads byte-identical, but it is intentionally not the production
archive.

## Windows and Linux portability boundary

Static review found no new platform-specific paths, fonts, APIs, or sizing assumptions in the repaired UI. The Qt layouts, scroll areas, keyboard focus, resource lookup, case-sensitive manifest paths, capture/production capability split, and scaling breakpoints are covered by the cross-platform test suite. This does not substitute for a Windows or Linux GUI run.

If live acceptance is later required on either platform, use the exact production SHA above in a fresh sync-disabled profile and check:

1. Deck Browser and Overview Home previews at 100%, 125%, 150%, and 200% display scaling.
2. Minimum/default/large Garden, Settings, Customize, Nursery, Progress, Story, and confirmation dialogs.
3. Tab order, focus rings, Escape/close behavior, scrolling to the final control, and all footer actions.
4. Plant grounding/crops in Home, 4:3, and 16:9 scenes, including all six spaces and every stage.
5. Save, close, restart, and persistence with no sync identity attached.

## Worktree and evidence boundary

The repository was already heavily modified when this release pass began. Those changes were treated as the candidate baseline and preserved through backup branch `backup/release-cleanup-20260815-212032Z` and tracked snapshot ref `refs/release-safety/20260815-212032Z` before work continued on `codex/release-optimize-20260813`. Nothing was reset or silently discarded.
