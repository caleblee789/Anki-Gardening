# Supported UI entry points

| Surface | Entry | Purpose | Failure behavior |
|---|---|---|---|
| Deck Browser | Anki Garden home card | Shows noninteractive garden art, nurtured-plant Growth, Anki streak, Garden Coins, and **Open Garden**. | Named artwork fallback and Retry appear for recoverable errors. |
| Deck Overview | Same home card below deck counts | Keeps the same compact status visible immediately before studying. | Idempotent legacy/modern hook injection prevents duplicates. |
| Add-on settings menu | **Caleb M. Add-ons Settings → Anki Garden settings** | Opens Anki Garden Settings. | Dashboard construction is retried before Settings is shown; failures do not change Anki data. |
| Home card | **Open Garden** | Opens the full Garden through Anki's webview bridge and resumes the saved onboarding step when setup is incomplete. | Unknown or foreign bridge messages pass through untouched. |
| Full Garden scene | Nursery building (`garden.nursery.open`) | Opens the tabbed catalog for starter selection, plants, Supplements & Boosters, Permanent Upgrades, and Weather & Scenery. | Unknown landmark actions fail closed. The target is disabled during Move and absent from home. |
| Full Garden scene | Cottage (`garden.collection.open`) | Opens Collection directly in the existing Garden Progress window. If that window is already open, it switches to Collection instead of creating a duplicate. | Uses the same fail-closed action registry and is disabled during Move/absent from home. |
| Selected plant card | **Nurture**, **Fertilize**, **Move**, **Story** | Routes future Growth, opens Nursery at Supplements, begins direct scene placement, or opens the plant timeline. | Disabled or failed actions explain the problem without mutating saved state. |
| Full Garden metrics | **Plant Growth**, **Anki streak**, **Garden Coins** | Each opens a focused read-only explanation with relative progress and exact rules. | Dialog failure leaves the Garden intact; focus returns to the originating button. |
| Full Garden | **Garden Progress** | Opens Garden Progress on its primary page; Collection remains available in the same window. | Opening/closing is transient and changes no persisted information. |
| Full Garden | **Collection** | Reuses Garden Progress and selects Collection directly. | Rapid activation is coalesced and never creates a second dialog. |
| Full Garden | **Settings** | Opens Garden naming, the current-style card, live preview, applicable Garden display/notification choices, and explicit Save/Cancel controls. Environment, quality/detail/performance, animation, and Fine tune choices are absent. | Existing settings remain active if saving fails or the learner cancels. |
| Settings | **Troubleshooting** tab | Refreshes and copies read-only diagnostics in production. An explicitly built, disposable capture package also exposes backup, populate, and restore development actions. | Missing telemetry produces an explanatory report; production cannot mutate garden state from this tab, and failed capture-build mutation preserves the prior backup/state. |

There is intentionally no reviewer-native button, toolbar action, duplicate
Nursery button, destination dropdown, Done-to-move action, Settings-based theme/weather selector, focus
timer, exam control, or deck-mapping UI in this release.
