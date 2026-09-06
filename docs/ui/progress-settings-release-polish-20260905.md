# Progress and Settings UI implementation

Contact sheet 4, surfaces 35–44, is implemented and verified against a packaged native Anki candidate. All ten requested surfaces pass their capture acceptance checks, with zero text or layout warnings. Save, Cancel, staged defaults, and persistence across a real Anki restart pass. The other four UI lanes still need the combined release capture after integration.

Coins remains its own page. The wooden trophy case is retained and refined. Artwork diagnostics remains a disclosure in Settings. This work changes presentation and navigation layout; progression, reward calculations, and sync behavior retain their existing authorities.

| Sheet surface | Implementation and disposition |
| --- | --- |
| 35 · Progress Today | Grouped cards studied, Growth, and Garden Finds inside the completion card beside the streak. Removed redundant completion copy and false “bonus” headings for neutral appearance. Displayed scenery and decoration are distinguished from any different bonus already active for the study day. |
| 36 · Today details | Bounded the details column, clarified the changing card total and study-day boundary, and moved View decorations beside the appearance heading. Preserved unavailable, waiting, no-due, and complete states supplied by the presenter. |
| 37 · Achievements | Compact, top-aligned content with smaller unboxed status icons. Consistent requirements, reward chips, completion dates, category rhythm, and “completed overall” count. Retained existing filters. |
| 38 · Achievements scroll end | Final singleton keeps the same width as other cards. Bottom content remains reachable. The native 860 × 580 check confirms all achievements are present, two readable columns, and no horizontal scrolling. A partially visible preceding card at the upper scroll boundary is ordinary scrolling, not clipped content. |
| 39 · Trophy Room | Kept the wood, original high-resolution artwork, lighting, and shadows. Reduced display height, aligned bases to the shelf, and made locked art recognizable. Added clear Locked/Unlocked/Active states, progress, requirements, permanent bonuses, and valid unlock dates. Narrow layouts pair each trophy bay with its details. Back to Garden uses shared action sizing. |
| 40 · Coins | Retained balance and a single Open shop action. Replaced ambiguous empty-state copy with “No coin history yet” and a concise explanation. Compact empty-state insets; filters are available whenever transaction history exists. Failed history loading retains its distinct retry state. |
| 41 · Settings | Simplified display and reward labels, preserved compact typography, and clarified that notifications do not affect earning rewards. Save remains disabled for an unchanged draft. Footer remains outside the scrolling body. |
| 42 · Unsaved settings | Quiet “Unsaved changes” indicator replaces a distracting change count. Native Save/Cancel checks prove draft isolation. The shared dialog owner supplied the workspace scrim, which dims navigation, scene, and footer consistently. |
| 43 · Diagnostics | Quiet borderless disclosure; shared compact height and measured icon-plus-label width. Health, timestamp, Check again, and Copy support report remain together. No duplicate internal scrolling. |
| 44 · Warning details | “Some artwork is missing” explains the user-visible condition. Technical support information stays inside the explicit disclosure. Report text wraps and the Settings body owns scrolling; footer controls remain visible. |

Shared implementation points for integration:

- `ui/dashboard.py`: local Today, Achievements, Coins, and Settings sections; `GardenSideNavigation` now measures tab labels and wraps without clipping; `_reserve_button_text_fit` now includes icon width and spacing.
- `ProgressCardGrid.add_category_group(..., span_singleton_row=True)` preserves other callers’ existing behavior. Achievements explicitly opts out of singleton spanning.
- `TodayCardsPageProjection.displayed_scenery_name` is a trailing defaulted field. The existing active scenery name keeps its original meaning.
- `ui/garden_studio.py`: six Settings copy replacements only.
- `ui/trophy_room.py` and `trophies.py`: responsive trophy presentation and concise requirements. Activation still comes from engine state.
- `presentation.py`: the diagnostics warning heading. Other presenter edits in the shared checkout belong to their respective lanes.
- `capture/runtime.py`: the achievement singleton check now expects one occupied column, while preserving the existing completeness checks. Other capture changes are shared work.
- Existing Settings geometry and compact-navigation assertions were updated. No new repository test files were introduced.

Verified candidate and evidence:

- Frozen source snapshot: `build/sheet4-progress-settings-vtmdoyk4/snapshot-03`.
- Production archive SHA-256: `adb9e63ac366fc7cc27a5f0a3baab1e392d8d35cf2e95542d2b701d4a507e676`.
- Package derivative report: `build/sheet4-progress-settings-vtmdoyk4/capture-03/package-derivative.json`.
- Final native capture manifest and ten PNGs: `build/sheet4-progress-settings-vtmdoyk4/capture-03/20260905-230034/`.
- Screenshot review page: `build/sheet4-progress-settings-vtmdoyk4/review.html`.
- Narrow achievement evidence: `capture-03/20260905-230034/progress-narrow/layout-audit.json` within the same lane directory.
- Native Save/Cancel/defaults and restart evidence: `build/sheet4-progress-settings-vtmdoyk4/settings-persistence/`. Both processes exited successfully; isolation checks passed before interaction and after restart. The temporary observer was removed from the disposable profile and never entered a candidate archive.
- Existing focused UI tests: 86 passed using Anki 26.8.1’s Qt runtime. The three existing Settings/compact-navigation/diagnostics checks also passed. Two integration follow-up assertions now reflect mounted Progress ownership and “Growth to Young”; both pass while retaining text-fit, containment, dialog isolation, and footer geometry checks. `git diff --check` passed.
- Earlier trophy layout checks covered 0, 1, and 3 unlocks at 1040, 720, 560, and 420 px. Those supplementary results predate the last copy/control-sizing refinements; final standard-width trophy evidence is the native candidate above.

All ten final PNGs were inspected at full resolution. Their surface acceptance is green. The scoped capture deliberately does not claim a complete release run: the global four-state dialog-scroll matrix requires surfaces from other sheets, so its run-level gate remains incomplete. Do not disable that gate or relabel this ten-surface set as a complete 51-surface release. Build the combined candidate after all five lanes settle, run the current v29 capture contract, and review the five final contact sheets together for cross-surface consistency. Later shared-source edits require a fresh candidate or validated capture reuse.
