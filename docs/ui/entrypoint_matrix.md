# Supported UI entry points

| Surface | Entry | Purpose | Failure behavior |
|---|---|---|---|
| Deck Browser | Anki Garden home card | Shows noninteractive garden art, the Garden name, nurtured plant and Growth, and **Open Garden**. Today’s Cards, Anki streak, and Garden Coins stay in their full-Garden/Progress surfaces. | Named artwork fallback and Retry appear for recoverable errors while **Open Garden** remains reachable. |
| Deck Overview | Same home card below deck counts | Keeps the same compact status visible immediately before studying. | Idempotent legacy/modern hook injection prevents duplicates. |
| Reviewer | Default-on Anki Garden HUD | Shows globally scoped Today’s Cards, prominent nurtured-plant art and six-stage checkpoint progress, next-answer Growth, compact active effects, one committed reward reveal, and the live local-session footer without taking focus. The expanded safe area is 296 px wide at top 44/right 16 with measured answer-control clearance and a 72 px fallback; narrow layouts collapse. Raw shares, environment names, Find caps, and irrelevant Stored Growth stay out of the persistent view. | Verification uncertainty uses `Card status unavailable` while normal Growth continues; render failure leaves Anki review controls untouched. |
| Reviewer HUD | Leaf/title, Coin balance, and collapse control | Opens the Garden or Nursery, or collapses the HUD to its edge tab. Dock side and collapse state persist. | Routine and delayed rewards never force the tab open or replay on rerender. |
| Add-on settings menu | **Caleb M. Add-ons Settings → Anki Garden settings** | Opens Anki Garden Settings. | Dashboard construction is retried before Settings is shown; failures do not change Anki data. |
| Home card | **Open Garden** | Opens the full Garden through Anki's webview bridge and resumes the saved onboarding step when setup is incomplete. | Unknown or foreign bridge messages pass through untouched. |
| Full Garden scene | Nursery building (`garden.nursery.open`) | Opens the tabbed catalog for starter selection, Plants, Fertilizers and boosts, Garden beds, and Garden Decorations and Scenery. | Unknown landmark actions fail closed. The target is disabled during Move and absent from home. |
| Full Garden scene | Cottage (`garden.collection.open`) | Opens Collection directly in the existing Garden Progress window. If that window is already open, it switches to Collection instead of creating a duplicate. | Uses the same fail-closed action registry and is disabled during Move/absent from home. |
| Selected plant card | **Nurture**, **Fertilize**, **Growth Charge**, **Move**, **Story** | Routes future Answer Growth, opens the source-plant-bound Fertilizer dialog, opens the target-specific Growth Charge dialog, begins scene placement, or opens the plant timeline. Fertilizer uses **Apply/Queue**, **Buy and apply/Buy and queue**, and same-tier-only **Extend**. | Disabled or failed actions explain the problem without mutating saved state; target identity may not change between quote, confirmation, and commit. |
| Full Garden metrics | **Plant Growth**, **Anki streak**, **Garden Coins** | Each opens a focused read-only explanation with relative progress and exact rules. | Dialog failure leaves the Garden intact; focus returns to the originating button. |
| Full Garden | **Garden Progress** | Opens Garden Progress on its primary page; Collection remains available in the same window. Collection keeps `10 of 10 species discovered` separate from `30 of 93 collection entries discovered` and includes earned beds, cosmetics, Landmark, and Mastery. | Opening/closing is transient and changes no persisted information. |
| Full Garden | **Collection** | Reuses Garden Progress and selects Collection directly, retaining distinct species and whole-registry counts. | Rapid activation is coalesced and never creates a second dialog. |
| Full Garden | **Settings** | Opens Garden naming, the current-style card, the structured Displayed decoration/Active garden bonus/Displayed scenery/Active scenery effect summary, applicable Garden display/notification choices including the persistent reviewer HUD, active major reward reveals, and the presentation-only Sync Rewards receipt, plus explicit Save/Cancel controls without duplicating the home preview. Environment selectors, quality/detail/performance, animation, and Fine tune choices are absent. | Existing settings remain active if saving fails, the name limit is violated, or the learner cancels. |
| Settings | **Diagnostics** tab | Refreshes and copies read-only diagnostics in production. An explicitly built, disposable capture package also exposes backup, populate, and restore development actions. | Missing telemetry produces an explanatory report; production cannot mutate garden state from this tab, and failed capture-build mutation preserves the prior backup/state. |
| Reviewer exit | Automatic Session Summary | Shows one upper-right nonmodal summary of proven local-session cards, daily progress, committed rewards, crossings/discoveries, and remaining effects. | The shared summary coordinator owns Escape and focus restoration; synced/background rewards are excluded. |
| Sync completion | Automatic Sync Rewards receipt | Shows one safely upper-right-docked, nonmodal summary of already-applied rewards from newly imported supported answers, with **Close** and **Open Garden** actions. Full Bloom, stage change, highest valid resulting-stage checkpoint, and ordinary Growth paint in deterministic order. | The shared coordinator replaces any Session Summary instead of overlapping it. The durable receipt survives restart until successfully mounted, never names a device, never leaks into Home banners, and can be hidden without suppressing reward processing. |

There is intentionally no reviewer-native button, toolbar action, duplicate
Nursery button, destination dropdown, Done-to-move action, Settings-based Garden Decoration/Scenery selector, focus
timer, exam control, or deck-mapping UI in this release.

The v26 evidence contract (contract schema 2, scenario schema 3) covers 18
representative and 38 full surfaces with two/six sheet pages. Scenario ID,
fixture ID, and one-based step are mandatory throughout lineage and v25 reuse
is rejected. Current run paths, archive and capture hashes, artifact sizes, and
validation totals are recorded only in the
[final 2.1.0 UI audit](final-ui-audit-2.1.0.md). This is frozen prerequisite
evidence and does not approve 2.2.0. It remains `quality_status:
review-required`, `release_ready: false`; manual, platform,
accessibility, mixed-DPI, keyboard, and human approval gates remain open.
