# Anki Garden 2.0 codebase audit

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

## Product focus

The supported experience is review-driven growth, streak/vitality feedback, daily quests, milestones, a local hand-painted scene, and appearance customization. Focus/exam/deck-mapping controls were removed from the visible product because they were incomplete and distracted from the primary loop. Legacy fields remain readable where needed to safely sanitize old payloads; they are not presented as supported features.

## Visual coverage

The manifest contains 76 backgrounds, 63 plant variants, 10 weather overlays, 5 decorations, and 3 UI assets, including the curated storybook-gouache slice. `scripts/audit_assets.py` enforces parsing, dimensions, uniqueness, and coverage. `scripts/build_asset_gallery.py` produces the full inspection gallery used alongside real-Anki theme, scaling, interaction, and fallback checks.

## Current validation snapshot

- 123 automated tests pass, including focus allocation, milestone claims, plant growth-display math, responsive layout, card interaction, and collection-not-ready startup behavior.
- The 165 manifest assets pass mixed-format signature, dimensions, uniqueness, coverage, alpha-family, and fallback checks.
- Python compilation, `.ankiaddon` packaging, ZIP integrity, source/archive parity, and `git diff --check` pass.
- A fresh disposable Anki 26.5 base verified clean startup, home-widget rendering, centered grounded plants, click-to-pin cards, Escape dismissal, arrow-key selection, Enter pinning, and absence of the former bottom roster.
