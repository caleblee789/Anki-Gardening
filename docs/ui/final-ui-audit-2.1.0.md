# Anki Garden 2.1.0 Final UI Audit

Status: historical frozen-release record, superseded for current visual coverage
by `docs/ui-release-overhaul-contract.md`. For the source audited here,
repository/package acceptance was complete and strict live acceptance remained
incomplete under an explicit owner-approved release boundary. Historical
capture contract v8 evidence was clean at 146/146 surfaces. The exact final
capture archive produced 139/146 uniform-primary screenshots and safely omitted
seven Home frames after macOS refused exact-window pixels; the owner authorized
proceeding without them. The frozen production archive passed every
repository-local package gate. Windows and Linux remained a static portability
review, not live GUI acceptance. Current source uses capture contract v18 with
191 ordered surfaces and a pending 24-sheet final run; this audit is not
evidence for it.

## Outcome

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
| Garden Progress | Today, Growth, streak, Coins, achievements, collection, milestones, empty states, and stress states | Clean; no remaining redundant or competing hierarchy found |
| Nursery and purchases | Plants, supplements, permanent upgrades, Weather/Scenery, owned/locked/success states, long rows, and confirmation dialogs | Clean; controls remain reachable above stable footers |
| Settings and Customize | Tabs, toggles, text fields, preview cards, Effects, diagnostics, validation, unsaved changes, disabled states, and production-only controls | Clean after Effects repair; capture-only control absent from production |
| Buttons and controls | Primary/secondary hierarchy, enabled/disabled states, footer alignment, keyboard focus, touch-target sizing, close actions, and switch clarity | Clean; production Settings measured 46 px for the visible Cancel and Save actions, above the 44 px minimum |
| Tabs and drop-down behavior | Tab labels, active states, responsive widths, keyboard reachability, and selection ownership | Clean; the internal hidden combo box is intentionally not learner-facing and no visible drop-down needed adjustment |
| Copy and repetition | Titles, helper copy, stage/Growth language, purchase terms, action casing, empty/error states, and accessible descriptions | Clean; essential accessible context remains self-contained rather than being removed as visual repetition |
| Color and visual hierarchy | V6 dark-green shell, mint actions/focus, gold brand accent, disabled states, artwork legibility, overlays, and scene-to-panel balance | Clean across normal, focus, disabled, reduced-motion, and stress captures; identity was refined rather than redesigned |
| Responsive and accessibility | Minimum/default/large windows, every declared breakpoint boundary, representative 150% and 200% scaling, keyboard focus, scroll reachability, and reduced motion | Clean with zero recorded geometry or text-layout warnings |
| State and recovery | Unsaved changes, validation failure, missing artwork, save status, production/capture separation, and settings persistence | Clean in automated and historical live evidence; the exact-final production restart was waived as documented below |

## Assets and preview sizing

The manifest-owned runtime audit reports 86 assets: 9 backgrounds, 1 decoration, 60 plant stage images, 9 UI assets, and 7 Weather assets. The final review covered the dedicated Home crops, 4:3 and 16:9 scene variants, all six plant spaces, every represented plant stage, Nursery/Story previews, watering-can positions, transparent artwork bounds, and missing-art fallback.

No asset or plant-preview resize was justified. Current preview crops preserve every landmark and bed; plant art remains grounded and readable without clipping or unintended upscaling; and changing sprite or card dimensions would risk the saved V6 geometry contract without solving an observed defect. The frozen production archive is 81,702,743 bytes (77.92 MiB), below the ratcheted 78 MiB ceiling, and its ZIP contains 262 files with 83,248,307 uncompressed bytes. The optimizer retains every manifest-owned image byte exactly.

## Capture evidence

- Contract: v8, full profile, requested Qt scale factor 1.5.
- Historical complete result: 146 expected, 146 captured, 0 failures, 0 text-layout warnings, quality `clean`; its 19 high-resolution contact sheets were visually reviewed.
- Historical complete visual-run capture-package SHA-256: `64d663b55610b44f4f6d15decd4175339306cd1f93eab25fd24ce4ba5c0a314e`.
- Exact final-source result: 139/146 uniform-primary screenshots, 0 text-layout warnings, and 7 safely omitted Home frames. The omitted labels are `active-overview-home-after-nurture` plus all six watering-can Deck Browser/Overview Home faces. A separate diagnostic captured the six watering-can Home faces 6/6 clean. The incomplete full manifest remains fail-closed and is not called a complete capture.
- Frozen explicit capture archive: 263 files, 81,737,735 bytes, SHA-256 `14114da87e24f4683bbcefdcdcca0ba2340263641d867bd9651bdbe7d28ddfeb`; ZIP integrity, capture-harness identity, and exact source parity pass.
- Capture images/contact sheets are ignored local build evidence and are intentionally not linked as durable repository files.
- The shared runner now builds this explicit capture archive with `--capture --output` and never touches the production artifact. Its retention logic prunes only proven-complete, strictly named evidence and preserves partial runs.

The capture build is deliberately different from the production archive because only the capture build contains the fail-closed screenshot harness. The production package excludes `capture_ui_faces.py` and reports production capabilities only.

## Automated validation

- Full repository suite: 1,536 passed in 84.21 seconds.
- Dedicated lossless pixel/container, planter, scene-profile, landmark, and item-art gate: 50 passed in 22.56 seconds.
- Asset manifest audit: 9 backgrounds, 1 decoration, 60 plants, 9 UI assets, 7 Weather assets.
- Python compilation: clean with a disposable bytecode cache.
- `git diff --check`: clean.
- Local Markdown links: clean.
- Production and explicit capture ZIP integrity plus exact ordered source parity: clean.
- Capture geometry and semantic Home audits: all saved frames clean; no geometry-warning records. Seven frames were omitted under the owner-approved boundary above.

## Exact-production macOS acceptance boundary

The frozen archive is `dist/anki_garden.ankiaddon`, SHA-256 `9d60b0d1b9523ca3f8c2b9e14be186c8b5ca19137f63064d1edfe15c99aa5b79`.

Repository-local validation proves its contents and production-only capabilities, but it does not substitute for an identity-gated GUI launch. An exact-production Anki 26.08.1 attempt used disposable profile `Anki Garden 2.1.0 Release 20260815-1711` and instance-key fingerprint `3fdbc25e59f9`. Process and filesystem identity passed, the exact add-on registered its hooks, and no pre-existing Anki process was controlled. The PID-owned window-title query returned no unique title, however, and the process opened a connection to `sync11.ankiweb.net` despite disconnected, auto-sync-off profile metadata. It was stopped immediately and was not restarted. Window, sync, and restart acceptance remain incomplete; the owner explicitly authorized release publication with that boundary.

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
