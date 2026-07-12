# Focused feature evidence matrix

This matrix is the release contract for Anki Garden 2.1. A feature is complete only when its automated gate passes and its live Anki 26.5 scenario is confirmed in a disposable, sync-disabled profile.

| Feature | Intended behavior | Automated evidence | Live acceptance |
|---|---|---|---|
| Startup and hooks | Start safely with or without an open collection; register menu, reviewer, sync, and home hooks once. | Startup/home and storage tests. | Clean launch, one Tools action, no startup warning. |
| Home card | Render once in Deck Browser and Overview; Open Garden and Refresh use scoped bridge commands; visibility changes immediately. | Home-state, injection, bridge, and visibility tests. | Both home surfaces, enable/disable, refresh, open. |
| Review ingestion | A live answer is counted once and saves its revlog cursor atomically; malformed hook values are bounded. | Engine and reviewer integration tests. | Answer Again and a correct rating; compare Anki and garden counts. |
| Synced review catch-up | Apply only unseen reviews from the current Anki day; historical rows advance the cursor without growth. | End-to-end and storage-query tests. | Seed current/historical revlog rows and refresh twice without duplication. |
| Daily rollover | Preserve same-day quests; reset daily counters on a new day; update a true consecutive-day streak and bounded vitality decay. | Engine rollover and quest regressions. | Seed previous-day state, restart, then answer one card. |
| Growth and focus | Every award is fully allocated; the focus plant receives 80% with deterministic remainder distribution. | Growth accounting and focus tests. | Nurture another plant, answer cards, compare both plants. |
| Quests and achievements | Progress from supported review metrics; rewards use the same growth-accounting path and cannot be awarded twice. | Engine quest and achievement tests. | Complete a seeded quest and due-card achievement. |
| Milestones | At 250/700/1500/2600 reviews, offer one stable unowned choice; claim exactly one plant and slot. | Milestone sequencing, stale-choice, and migration tests. | Seed each ready/completed state and claim a choice. |
| Plant stages | Growth thresholds, rare stage, transition messaging, and resolved artwork agree. | Growth display, transition, asset, and SVG guardrail tests. | Cross a threshold and confirm scene/home artwork and message. |
| Plant interaction | Hover/pin, Nurture, move to empty slot, swap, cancel, one-level undo, and save rollback work with mouse and keyboard. | Placement engine and interaction-state tests. | Mouse and keyboard journeys, including invalid drop and Undo. |
| Accessibility | Arrow keys navigate; Enter/Space activate; Escape cancels; Tab/Shift+Tab leave the scene; selected actions and destinations have visible focus. | Interaction source/geometry regressions. | Keyboard-only pass and macOS accessibility inspection. |
| Settings | Daily goal, home visibility, theme, quality, animation, and weather detail validate and save transactionally. | Configuration validation/rollback and home visibility tests. | Change every control, force refresh, restart, verify persistence. |
| Persistence | v6 migrates to v7 while preserving visible progress; malformed layouts repair; invalid/unsupported files are backed up. | State contract and storage migration tests. | Upgrade seeded v6 state and inspect `user_files/` backups. |
| Artwork and layout | Bundled local assets render with safe fallback, responsive geometry, light/dark readability, and reduced motion. | Asset audit, geometry, fallback, and package tests. | All themes, narrow window, light/dark mode, reduced motion. |
| Packaging | Archive contains current runtime/assets and excludes mutable progress/cache; source and archive match byte-for-byte. | Package, ZIP, and parity gates. | Install the exact rebuilt archive into the disposable profile. |

## Unsupported systems

Focus timers, exam mode, deck mapping, shop/currency, weekly events, mastery, rare events, passive rewards, and remote/social/cloud systems are not release features. Their v6 keys are intentionally ignored during migration and are absent from the v7 serializer and engine interface.
