# Display validation matrix

| Surface value | Source | Transform and fallback |
|---|---|---|
| Reviews today | Current Anki-day revlog answer count | Counts every supported answer event (revlog types 0–3) after scheduler-day start; falls back to persisted daily reviews. |
| Streak | `GardenState.streak_days` | Increments on the first answered card of a new active day. |
| Garden vitality | Engine health aggregate | Clamped percentage; earned plant progress is never removed. |
| Daily growth | `daily_stats.growth_earned` / configured goal | Percentage clamps at 100%; growth continues beyond the goal. |
| Weather | `selected_weather` | Friendly title-case label and local overlay fallback. |
| Plant thumbnails | Manifest-selected SVG | Exported `/_addons/...` URL in webviews; emoji fallback. |
| Plant composition | Shared placement metadata and slot order | One-to-six plants remain grounded, collision-free, and depth ordered in both the dashboard and home widget; missing artwork keeps a named stage-appropriate fallback. |
| Plant stage/growth | Plant growth points | The plant card shows stage progress in full words, plain-language plant health, the next stage, and a proportional progress bar; flowering/rare states show fully grown. |
| Plant interaction | Stable plant ID plus painted selection and native Qt actions | The scene selects and optionally drags plants; a focusable action panel provides Nurture, Move, View story, Cancel move, and status semantics. Preview scenes are explicitly noninteractive. |
| Nurtured plant | Valid `focus_plant_id` | A grounded glow/ring identifies it without covering the artwork; the adjacent focus summary explains that it receives 80% of future growth, and invalid IDs repair to the first slot. |
| Garden milestone | Total reviews plus persistent pending reward | Home shows progress/readiness; dashboard offers up to three stable unowned species and claims one slot at a time. |
| Plant story | Stable plant ID plus semantic milestone memories | View story opens a keyboard-accessible detail dialog with generated/editable name, planted date, current growth, and newest-first warm factual timeline. |
| Quest progress | Daily quest metric | Preserved through same-day restart; regenerated only at rollover. |
| Appearance | Whitelisted Anki add-on config | Guided, documented preferences save transactionally; the labeled Preview only scene is removed from the tab order. |
| Responsive layout | Available dialog/webview geometry | Dashboard content scrolls, settings controls stack above the preview below 720 px, home metrics collapse to one column, and cards and overlays remain inside unusually small scenes. |

Strict acceptance requires Deck Browser, Overview, dashboard, persisted state, and Anki's own studied-today count to agree after a real review.

The former bottom roster is intentionally removed. Plant data has one authoritative presentation in the interactive scene rather than a duplicated dashboard section.
