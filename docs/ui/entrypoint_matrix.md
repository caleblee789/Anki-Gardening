# Supported UI entry points

| Surface | Entry | Purpose | Failure behavior |
|---|---|---|---|
| Deck Browser | Anki Garden home card | Shows noninteractive garden art, nurtured-plant Growth, Anki streak, Garden Coins, and **Open Garden**. | Named artwork fallback and Retry appear for recoverable errors. |
| Deck Overview | Same home card below deck counts | Keeps the same compact status visible immediately before studying. | Idempotent legacy/modern hook injection prevents duplicates. |
| Tools menu | **Tools → Anki Garden** | Opens the full responsive Garden. | Startup and render errors are logged without changing Anki data. |
| Home card | **Open Garden** | Opens the full Garden through Anki's webview bridge. A fresh garden then auto-opens Nursery for starter selection. | Unknown or foreign bridge messages pass through untouched. |
| Full Garden scene | Nursery building (`garden.nursery.open`) | Opens the artwork-led Nursery for free starter selection, collection management, release-ready plant purchases, and space unlocks. | Unknown landmark actions fail closed. The target is disabled during Move and absent from home. |
| Selected plant card | **Nurture**, **Fertilize**, **Move**, **Story** | Routes future Growth, opens Fertilizer cards, begins direct scene placement, or opens the plant timeline. | Disabled or failed actions explain the problem without mutating saved state. |
| Full Garden | **Progress** | Expands or collapses Today, Achievements, Collection, detailed Growth, and Garden Coin activity. | A newly constructed Garden starts collapsed; expansion is transient and changes no persisted information. |
| Full Garden | **Settings** | Opens the current-style card, live preview, Garden display, Motion, Fine tune, and explicit Save/Cancel controls. | Existing settings remain active if saving fails or the learner cancels. |
| Settings | **Troubleshooting** tab | Refreshes and copies display diagnostics without changing Garden state. | Missing telemetry produces an explanatory report rather than blocking Settings. |

There is intentionally no reviewer-native button, toolbar action, duplicate
Nursery button, destination dropdown, Done-to-move action, theme store, focus
timer, exam control, extra currency, or deck-mapping UI in this release.
