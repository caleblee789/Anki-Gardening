# Anki Garden 2.1 codebase audit

This ledger records the comprehensive stabilization and product rework. The
schema 14 / Verdant Twilight V6 section is current; later dated sections are
historical evidence for older packages and do not describe the present UI or
progression contract.

## 2026-08 progression overhaul

| Area | Current resolution | Verification |
|---|---|---|
| Progression | One answer produces 10 base Growth for one answer-time nurtured unfinished plant; Nurture changes only future routing, with no split, movement, regression, or Rare overflow. | Engine routing, threshold, terminology, bonus-rounding, and balance-profile tests. |
| Streak Growth | A missed Anki day resets the next streak to day 1; the current streak adds 0/5/10/15/20/25% at days 1/7/14/30/100/365. | Exact tier-boundary, reset, fractional-rounding, and UI contract tests. |
| All due | Live collection-wide Anki due tree plus introduced learning/relearning through cutoff; unseen new and unavailable suspended/buried excluded; filtered decks included; one answer required; once/day and no revoke. | Due-tree/SQL semantics and reward tests; exact-package runtime scenario required. |
| Fertilizer | Plant-specific elapsed-time Fertilizer directly adds +1/+2/+3 Growth per answer only from its persisted activation time through its exclusive expiry; same tier extends one interval, while replacement or expired repurchase archives the prior interval for late synced answers. | Price/tier/timer/pre-during-post sync/expiry/extension/replacement/history/restart tests. |
| Economy | The internal `currency_balance` ledger records every reason and balance; learner-facing UI consistently says Garden Coins. All-due/streak/stage rewards fund Fertilizer, release-ready species, and spaces. | Terminology, idempotence, debit/rollback, and 50/150/300/500-answer simulations. |
| Information architecture | Home shows only noninteractive art, nurtured-plant Growth, streak, Coins, and Open Garden. The Garden keeps a three-metric strip and collapsed Progress; the compact selected-plant card owns plant details. | Home/Garden source contracts, content-ownership, and render tests. |
| Nursery | The manifest landmark is the only normal Nursery entry, fresh Garden auto-opens it, and stock is derived from complete release-preferred V6 lines without a hard-coded denominator. | Landmark, starter, catalog-readiness, legacy-owned, transaction, and accessibility tests. |
| Interaction | Restrained artwork-bound hover, one selected card, Nurture/Fertilize/Move/Story, direct scene placement, immediate save, and temporary Undo. No destination dropdown or Done action remains. | Interaction, hitbox, card geometry, placement, rollback, source-contract, and responsive tests. |
| Story and Settings | Story is oldest-to-newest with inline rename and Up next. Settings has a read-only current-style card, live preview, collapsed Fine tune, explicit Save/Cancel, and preserved Troubleshooting. | Story ordering/empty/accessibility tests and config dirty/default/cancel/save/responsive tests. |
| State boundary | Schema 10 is backed up and converted; schemas 11–13 migrate into schema 14 as established gardens; a migration-pending marker atomically seeds the bounded current-day revlog ID ledger before catch-up. Corrupt/unsupported saves are backed up, and removed quest/focus/score/goal systems remain absent. | Migration matrix, two-restart ledger seed, late lower-ID sync, starter migration, backup/recovery, malformed-state, repeated-round-trip, and package tests. |
| V6 environment | Verdant Twilight V6 provides six direct-soil spaces, responsive masters, occlusion, and generic landmark dispatch. Bonsai, Rose, Sunflower, Lavender, Hydrangea, Peony, Foxglove, Japanese Maple, Wisteria, and Dahlia are the current complete acquisition lines. | Asset audit, geometry/layout matrices, catalog readiness, responsive renders, and package checks. |

## Historical stabilization findings

The following rows describe problems and fixes in superseded pre-schema-13
packages. They remain useful engineering history; their themes, controls,
terminology, test counts, and progression models are not current requirements.

| Area | Finding | Resolution | Verification |
|---|---|---|---|
| Persistence | Progress and asset metadata were written beside add-on source and could be deleted by an upgrade. | Mutable files now live under `user_files/`; unreadable and legacy state is preserved before a clean reset. | Storage and package tests; isolated reinstall/restart QA. |
| Progression | The hard daily cap made reviews stop growing the garden without explaining why. | The configured value is now a motivational daily goal; growth continues after completion. | Engine tests above-goal reviews. |
| Rewards | Quest and focus growth bypassed the displayed daily-growth total. | All awards flow through one accounting function. | Quest accounting tests. |
| Sync | Historical synced reviews could be presented as work completed today. | The retrospective cursor advances for old rows, while only current Anki-day rows are applied. | Integration tests and isolated sync/startup smoke. |
| Home UI | Refresh and retry controls had no behavior. | Buttons use named Anki bridge commands for refresh and opening the garden. | Hook tests and live Deck Browser/Overview QA. |
| Web artwork | `file://` plant thumbnails appeared broken in Anki's webview. | SVGs are registered as Anki web exports and referenced through `/_addons/...`. | Packaged Deck Browser and Overview screenshots. |
| Reviewer | A native Qt button was inserted into an incompatible modern reviewer bottom bar and raised an Anki error. | Removed the unsupported reviewer injection; Tools and home actions are the stable entry points. | Real card question/answer/rating pass on Anki 26.5. |
| Settings | Visual controls changed a preview but were never saved or applied. | Garden appearance has an explicit save action backed by `writeConfig`; dashboard rendering consumes the settings. | Restart persistence QA. |
| Daily quests | Startup regenerated same-day quests and discarded visible progress. | Initialization preserves existing quests; only day rollover regenerates them. | Restart regression test and isolated restart QA. |
| Layout | A fixed four-column dashboard could not fit the declared minimum window. | The page is scrollable and the secondary row is reduced to three focused cards. | Small-window visual QA. |
| Animation | The scene timer ran continuously, including while hidden or when animation was disabled. | Motion follows settings and stops when the widget is hidden. | Scene tests and runtime observation. |
| Assets | Placeholder generation could mutate packaged artwork. | No placeholder bitmap is shipped; unresolved art remains a named, stage-aware plant rendered by code-native fallback UI. | Asset and package tests. |
| Packaging | There was no reproducible `.ankiaddon` build and `meta.json` was tracked as source. | Added a distribution manifest, deterministic builder, exclusions, archive tests, and full CI checks. | Package test plus archive integrity check. |
| Plant interaction | Plants read as floating cutouts and their data was duplicated in a distant roster. | Added alpha-aware ground anchors, attached contact shadows, stationary selected-state emphasis, contextual actions, click-to-pin behavior, and keyboard navigation; removed the duplicate roster. | Plant-display interaction tests plus isolated dashboard QA. |
| Startup timing | Retrospective review discovery could query `mw.col.db` before a collection existed and log an avoidable startup exception. | Collection-dependent retrospective and storage queries now no-op until Anki has a live collection/database. | Storage regression test and clean disposable-profile startup. |
| Progression | Growth was divided equally, plant interaction did not affect future progress, and slot unlocks happened invisibly. | Added a repaired focus-plant invariant, exact-total 80/20 growth allocation, persistent milestone choices, and home/dashboard progression feedback. | Engine allocation/reward tests, state-contract tests, and home-widget assertions. |
| State contract | Hidden v6 focus, exam, shop, event, mastery, and recovery flags could still alter the supposedly focused core. | Added a progress-preserving v6→v7 migration and removed dormant fields and engine entry points from the persisted/runtime contract. | Migration, serializer, hidden-interface, and package tests. |
| State integrity | Duplicate IDs/slots, invalid focus IDs, and incoherent unlocked-slot counts could break movement or milestones. | Load-time repair now assigns deterministic unique IDs/slots, clamps bounds, repairs focus, and reconciles unlocked spaces. | State-contract and placement tests. |
| Settings | Malformed config values could crash rendering, and `writeConfig` failure left unsaved values active in memory. | Added a typed whitelist with bounded values and persist-before-activate transactions; daily goal and home visibility are now first-class controls. | Configuration validation/rollback and home-injection tests. |
| Review ingestion | Malformed hook values could abort the reviewer callback, and the revlog cursor was saved separately from progress. | Normalize/bound review inputs, register hooks idempotently, and save live/catch-up progress with its cursor in one transaction. | Engine failure/normalization, hook, and retrospective tests. |
| Plant arrangement | The new move/swap work lacked full rollback, keyboard exit, and visible action-focus guarantees. | Preserve atomic move/swap/undo, cancel placement on focus traversal, let Tab leave normally, and render the selected action/destination focus. | Placement/interaction regressions plus isolated keyboard/mouse QA. |
| Plant attachment | Plants had growth and interaction but no durable individual identity or history. | Added generated/editable names and semantic, deduplicated milestone stories opened from each plant's action card; stories use study activity only. | State, engine, rename, scene-action, package, and isolated dialog/restart QA. |
| Settings layout | The fixed side-by-side preview could crowd or hide controls at small window sizes, and appearance-only wording omitted goal/home behavior. | Added a scrollable settings viewport, deterministic 720 px stack breakpoint, visible slider values, accessible control names, and accurate Garden settings copy. | Responsive helper tests plus isolated wide-window settings inspection. |
| Home accessibility | Loading/error states lacked normal card spacing and the progress bar exposed no semantic value. | Unified transient-state containers, status/alert roles, keyboard focus styling, labeled actions, and progressbar values. | Home render-state assertions plus isolated accessibility-tree inspection. |
| Artwork fallback | A plant with a completely failed resolver could be omitted before the renderer had a chance to show its stage fallback. | Preserve named plant composition with an empty artwork URL and stage-aware fallback. | Home-scene resolver-failure regression and HTML fallback tests. |
| Cross-surface refresh | Settings and plant mutations refreshed the dashboard but could leave the existing Deck Browser card stale. | Store the explicit Anki main-window reference and refresh external web surfaces after settings, rename, nurture, placement, undo, and reward mutations. | Mutation-path regression plus isolated settings/home comparison. |
| Focus presentation | Floating Nurturing pills covered the garden artwork and weakened immersion. | Kept nurturing status in the accessible action panel and reserved the restrained ground outline for the currently selected plant. | Scene/home source assertions and isolated dashboard/home visual inspection. |
| Scheduler compatibility | Eager evaluation touched deprecated `dayCutoff` even when modern `day_cutoff` existed. | Resolve the modern property first and use the legacy property only when required. | Deprecation-access regression plus clean Anki 26.05 startup log. |
| Plant actions | Painted rectangles looked like controls but lacked native button semantics and reliable keyboard focus. | Moved Nurture, Move, Story, and Cancel move into a native compact `PlantActionPanel`; the scene now owns only selection and placement targets. | Behavioral placement tests, primary-button filtering, preview mode, and packaged Qt QA. |
| Review count | The prominent home count used distinct cards, disagreeing with growth when a card was answered more than once. | Renamed the contract to `reviews_today` and count every supported revlog answer event in the current Anki day. | Home builder/query tests. |
| Goal changes | An earlier development build exposed a configurable daily goal. | Retired during the schema-12 simplification; current Currency rewards use all-due completion, streak milestones, and plant stages. | Current engine and serializer tests assert the removed fields are absent. |
| Recoverable failures | Garden-save failures during review were log-only even though the Anki answer succeeded. | Added a throttled session notice shared by reviewer feedback, dashboard status, and home card. | Reviewer and render contract tests. |
| Progress details | Milestones and Collection mixed achievements with an incomplete inventory surface. | Renamed the progress surface to Achievements, added criteria/progress/unlock dates, and removed Collection. | Dashboard behavior/package inspection. |

## Current product focus

The supported experience is review-driven single-plant Growth, Nurture routing,
streak-tier bonuses, all-due/streak/stage Garden Coins, time-based Fertilizer,
data-driven Nursery stock, six direct-soil spaces, local Plant Stories, direct
Move and Undo, same-scheduler-day catch-up, a calm three-metric Garden, and
staged display/motion settings. The configured roster contains ten species, but
the UI shows only computed collected and available-now counts. Focus timers,
exam mode, deck mapping, extra currencies, plant death/regression, passive
rewards, separate rare variants, weekly events, mastery, and social/cloud
systems are absent.

## Visual coverage

The manifest contains one Verdant Twilight V6 environment, 60 current plant
sprites, 10 weather overlays, and one lantern. `scripts/audit_assets.py` is the
count and validity source of truth and rejects unreferenced runtime files.
Nursery readiness applies a strict complete-six-stage V6 rule, while a
configured or previously owned species remains state-safe even when no old
bitmap is bundled.

## Current validation gates

- Run the complete pytest suite, asset audit, Python compilation, package build, ZIP integrity, source/archive parity, and `git diff --check`; do not rely on a hard-coded historical test or asset count.
- Install the exact rebuilt archive into a disposable, sync-disabled Anki 26.08 base/profile and verify every live scenario in `feature-evidence-matrix.md`.
- Record the final package hash, automated results, and live acceptance result here after the release pass.

## 2026-07-12 release acceptance

The following acceptance record predates the unreleased v8 Plant Stories reset and remains historical evidence for the underlying 2.1 core. Plant Stories require a fresh packaged acceptance pass.

- Automated gates: 157 tests passed; the asset audit reported 78 backgrounds, 69 plant variants, 10 weather overlays, 5 decorations, and 3 UI assets; compilation and `git diff --check` passed.
- Package gates: ZIP integrity and byte-for-byte parity passed for all 196 packaged files. SHA-256: `7866c3491899829f1584da45008fdca67cd3fad58aaaba59e1dfebf8c5d5d21d`.
- Anki 26.05 fresh-profile pass: startup completed without an add-on error after correcting generated-hook registration; one Tools action, both home-card states, immediate visibility changes, a real Anki card through the reviewer hook, focus selection, move/swap/undo, milestone claim, settings save, reduced motion, and minimum-size dashboard rendering passed.
- Anki 26.05 interaction pass: real Qt mouse pin/nurture/drag events and keyboard move/undo, Tab exit, Escape dismissal, and visible action focus passed in the isolated dashboard.
- Anki 26.05 migration/restart pass: seeded v6 totals, daily stats, plants, focus, quests, appearance, and review cursor migrated to v7; the untouched v6 backup remained; unsupported fields were absent; settings, home rendering, dashboard rendering, and reduced motion persisted after restart.
- Isolation: every successful runtime pass used a separately keyed disposable base/profile with sync unused. The existing normal Anki window was never controlled.

## 2026-07-12 Plant Stories release-candidate acceptance

- Automated gates: 180 tests passed; compilation, the full asset audit, and `git diff --check` passed.
- Package gates: ZIP integrity and byte-for-byte parity passed for all 196 packaged files. SHA-256: `bf38a8b403e4e4ec43d340a90da4bdaef4824b77200d9ddb0485655bb04e1d89`.
- Anki 26.05 startup/display pass: the exact packaged artifact loaded in a separately keyed, sync-disabled disposable base/profile; one Tools action, Deck Browser and Overview cards, the responsive dashboard, appearance settings, dark presentation, and restart registration rendered without an add-on warning.
- Plant interaction and Stories pass: mouse-opened action cards, keyboard swap and immediate undo, story artwork/timeline, inline rename, first-nurture memory, focus selection, and restart persistence passed. The first-use interaction hint dismissed and persisted after use.
- Review/state pass: a real disposable card updated review totals, quests, streak, weather, and exact 80/20 plant growth. Seeded v7 state was retained as `garden_state.legacy.json`, reset to v8, and current-day revlog rows were replayed once without duplication.
- Defects found and re-verified: Qt 6 tooltip events returned `QPoint` values incompatible with `QRectF.contains`, and live/catch-up review paths derived card type and zero-factor difficulty differently. Both paths now normalize Qt points and use the same authoritative revlog semantics; two catch-up learning answers earned 8 growth and the next live learning answer earned 4.
- Isolation: the normal Anki profile was never controlled or modified.

## 2026-07-12 comprehensive UI-surface acceptance

- Automated gates: 191 tests passed; compilation and `git diff --check` passed. The asset audit reported 78 backgrounds, 69 plant variants, 10 weather overlays, 5 decorations, and 3 UI assets.
- Package gates: ZIP integrity and byte-for-byte source parity passed for all 196 packaged files. SHA-256: `07dea1be46e916d31d13d1d7b0cab10751d95e18c9d0f70aa5edb5a7a6e0b844`.
- Anki 26.05 display pass: the exact package rendered the Deck Browser card, responsive dashboard, grounded focus treatment, action card, wide settings preview, 640×460 stacked settings controls, Advanced diagnostics, and Plant Story without an add-on warning.
- Accessibility and interaction pass: the home card exposed a named region, labeled Open/Retry actions, status/alert semantics, and a numeric progress indicator; keyboard navigation opened Plant Story, and a maximum-length plant name remained available to the accessibility tree without clipping controls.
- Mutation/restart pass: a settings mutation updated the already-rendered Deck Browser card from a 150-point to a 170-point goal; the UI-saved Morning Bloom theme, animation state, 150-point goal, and `Moss the Patient Study Companion` name survived installation into a new disposable base and restart.
- Defects found and re-verified: stale external home surfaces now refresh through the stored Anki main-window reference; complete plant-asset resolution failures retain named fallback plants; passive home renders no longer consume stage transitions; modern `day_cutoff` no longer touches the deprecated property; floating Nurturing pills were replaced by accessible action-panel status and stationary selection emphasis.
- Isolation: every live pass used separately keyed disposable bases with sync unused. The normal Anki profile was never controlled or modified.

## 2026-07-12 native-action remediation acceptance

- Automated gates: 193 tests passed; the asset audit reported 78 backgrounds, 69 plant variants, 10 weather overlays, 5 decorations, and 3 UI assets; compilation, gallery generation, ZIP integrity, and `git diff --check` passed.
- Package: 198 packaged files with zero source/archive mismatches. SHA-256 `03bcc8bb7d09a227fda5ee0183e2fb14270528fdf6f766c01d4dd50a0e50d089`.
- Resolved in this pass: native contextual plant actions, primary-button filtering, keyboard move/cancel, preview-only scenes, answer-event review counting, goal/quest reconciliation with rollback, detailed Achievements, recoverable save notices, adaptive home-card colors, guided configuration documentation, local Plant Story dates, and Troubleshooting report copy.
- Anki 26.05 isolated pass: a fresh separately keyed base/profile loaded the rebuilt add-on without an add-on warning. The Deck Browser card and Tools entry rendered, the dashboard selected and nurtured a plant, keyboard movement swapped two plants with specific feedback, native Undo restored them, and Cancel move appeared as a focusable action.
- Story/settings/accessibility pass: Plant Story rendered artwork and locally formatted dates, accepted and announced an accented emoji rename, and exposed its timeline to the accessibility tree. The settings preview exposed no actions, Troubleshooting showed real line breaks and Copy report, and Save completed successfully.
- Restart pass: the renamed plant, nurturing choice, home card, Tools action, and dashboard state survived a full disposable-process restart. Live inspection found motion controls were still enabled while animation was off and weather detail exceeded the renderer range; both were corrected, rebuilt, and rechecked in the exact final package, where the sliders became disabled and the spin box/home visibility controls had accessible values.
- Isolation: the first attempt was abandoned immediately when Anki forwarded to the normal-profile window; no control was used there. Every successful interaction used `/private/tmp/anki-garden-ui-qa-retry.uoryX1`, a unique single-instance key, and sync was never used. The normal profile was not modified or controlled.

## 2026-07-12 first-use clarity release-candidate verification

- Automated gates: 204 tests passed; the asset audit reported 78 backgrounds, 69 plant variants, 10 weather overlays, 5 decorations, and 3 UI assets; compilation, gallery generation, and `git diff --check` passed.
- Package gates: ZIP integrity and byte-for-byte parity passed for every changed runtime file. SHA-256: `ab66d7bce7e1fd0b471816ecfec1237fcc817eab5a5d989c241340925017ca83`.
- Candidate behavior: versioned inline guidance covers the first review and first Nurture action, legacy completed hints migrate without reappearing, dismissal is transactional, and no onboarding state enters `garden_state.json`.
- Live acceptance pending: the disposable Anki pass stopped before launch because the environment could not complete the required pre-existing-process identity check. No Anki window or normal profile was controlled; fresh launch, real-review advancement, Nurture completion, accessibility, and restart persistence remain to be confirmed on this exact package.

## 2026-07-30 first-use repair verification

- Automated gates: 204 tests passed; the asset audit reported 78 backgrounds, 69 plant variants, 10 weather overlays, 5 decorations, and 3 UI assets; compilation, gallery generation, and `git diff --check` passed.
- Package gates: ZIP integrity and byte-for-byte parity passed for all 198 packaged files. SHA-256: `9759b9a98713b2c3a940c88f5bb56e6e90a37a75c2d6de0dfed2c29af35153c7`.
- Resolved in this pass: first-use guidance now completes and persists after Nurture; stale confirmation timers are generation-guarded; failed onboarding writes remain visible; legacy preferences are removed on the next successful write; active Deck Browser/Overview renderers refresh explicitly after dashboard mutations and close; local test launchers no longer reference the old checkout; and the generated status report no longer embeds a stale test count.
- Exact-package interaction pass: one real Good review changed the home card to 1 review and 4 growth, advanced quests and milestones, and exposed the post-review Nurture guidance. Selecting Rose and choosing Nurture produced the completion confirmation, a first-focus Story memory, and the 80% focus state. Rename, native Story controls, progress semantics, disabled motion controls, and settings-save status were present in the accessibility tree.
- Cross-surface and restart pass: the review totals, focus plant, onboarding completion, renamed plant, Story memories, and disabled animation setting survived controlled restart. Live QA found that `mw.reset()` alone left the already-open home card stale; the final candidate explicitly refreshes the active Deck Browser/Overview renderer, and renaming the focus plant to `Briar Verified` updated the open Deck Browser card immediately without restart.
- Isolation: Anki 26.5 used `/private/tmp/anki-release-qa.vux811/base`, profile `Codex QA 20260730-anki-release-qa.vux811`, and a unique single-instance key with sync unused. Process, window, filesystem, and sync gates passed before interaction and after restart. The pre-existing normal Anki PID remained open and was never controlled or modified.
