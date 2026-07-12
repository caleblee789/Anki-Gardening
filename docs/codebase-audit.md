# Anki Garden 2.1 codebase audit

This ledger records the comprehensive stabilization and focused-product rework.

## Resolved high-impact findings

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
| Assets | Placeholder generation could mutate packaged artwork. | The bundled fallback is read-only; emergency generation uses the user cache. | Asset and package tests. |
| Packaging | There was no reproducible `.ankiaddon` build and `meta.json` was tracked as source. | Added a distribution manifest, deterministic builder, exclusions, archive tests, and full CI checks. | Package test plus archive integrity check. |
| Plant interaction | Plants read as floating cutouts and their data was duplicated in a distant roster. | Added soil contact, directional shadows, foreground grass, persistent rim separation, hover/focus emphasis, contextual data cards, click-to-pin behavior, and keyboard navigation; removed the duplicate roster. | Plant-display interaction tests plus isolated dashboard QA. |
| Startup timing | Retrospective review discovery could query `mw.col.db` before a collection existed and log an avoidable startup exception. | Collection-dependent retrospective and storage queries now no-op until Anki has a live collection/database. | Storage regression test and clean disposable-profile startup. |
| Progression | Growth was divided equally, plant interaction did not affect future progress, and slot unlocks happened invisibly. | Added a repaired focus-plant invariant, exact-total 80/20 growth allocation, persistent milestone choices, and home/dashboard progression feedback. | Engine allocation/reward tests, state-contract tests, and home-widget assertions. |
| State contract | Hidden v6 focus, exam, shop, event, mastery, and recovery flags could still alter the supposedly focused core. | Added a progress-preserving v6→v7 migration and removed dormant fields and engine entry points from the persisted/runtime contract. | Migration, serializer, hidden-interface, and package tests. |
| State integrity | Duplicate IDs/slots, invalid focus IDs, and incoherent unlocked-slot counts could break movement or milestones. | Load-time repair now assigns deterministic unique IDs/slots, clamps bounds, repairs focus, and reconciles unlocked spaces. | State-contract and placement tests. |
| Settings | Malformed config values could crash rendering, and `writeConfig` failure left unsaved values active in memory. | Added a typed whitelist with bounded values and persist-before-activate transactions; daily goal and home visibility are now first-class controls. | Configuration validation/rollback and home-injection tests. |
| Review ingestion | Malformed hook values could abort the reviewer callback, and the revlog cursor was saved separately from progress. | Normalize/bound review inputs, register hooks idempotently, and save live/catch-up progress with its cursor in one transaction. | Engine failure/normalization, hook, and retrospective tests. |
| Plant arrangement | The new move/swap work lacked full rollback, keyboard exit, and visible action-focus guarantees. | Preserve atomic move/swap/undo, cancel placement on focus traversal, let Tab leave normally, and render the selected action/destination focus. | Placement/interaction regressions plus isolated keyboard/mouse QA. |
| Plant attachment | Plants had growth and interaction but no durable individual identity or history. | Added generated/editable names and semantic, deduplicated milestone stories opened from each plant's action card; stories use study activity only. | State, engine, rename, scene-action, package, and isolated dialog/restart QA. |

## Product focus

The supported experience is review-driven growth, streak/vitality feedback, daily quests, milestones, local plant stories, a hand-painted scene, plant care/arrangement, and appearance customization. Focus timers, exam mode, deck mapping, shop/currency, weekly events, mastery, rare events, and passive rewards are absent from the v8 state and engine contract.

## Visual coverage

The manifest contains the complete background, plant-stage, weather, decoration, and UI catalogs, including the curated storybook-gouache slice. `scripts/audit_assets.py` is the count and validity source of truth; it enforces parsing, dimensions, uniqueness, coverage, alpha-family, and fallback requirements. `scripts/build_asset_gallery.py` produces the inspection gallery used alongside real-Anki theme, scaling, interaction, and fallback checks.

## Current validation gates

- Run the complete pytest suite, asset audit, Python compilation, package build, ZIP integrity, source/archive parity, and `git diff --check`; do not rely on a hard-coded historical test or asset count.
- Install the exact rebuilt archive into a disposable, sync-disabled Anki 26.5 base/profile and verify every live scenario in `feature-evidence-matrix.md`.
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
