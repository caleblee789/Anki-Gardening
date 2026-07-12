# Display validation matrix

| Surface value | Source | Transform and fallback |
|---|---|---|
| Cards today | Current Anki-day revlog count | Distinct card count after scheduler-day start; falls back to persisted daily reviews. |
| Streak | `GardenState.streak_days` | Increments on the first answered card of a new active day. |
| Garden vitality | Engine health aggregate | Clamped percentage; earned plant progress is never removed. |
| Daily growth | `daily_stats.growth_earned` / configured goal | Percentage clamps at 100%; growth continues beyond the goal. |
| Weather | `selected_weather` | Friendly title-case label and local overlay fallback. |
| Plant thumbnails | Manifest-selected SVG | Exported `/_addons/...` URL in webviews; emoji fallback. |
| Plant composition | Shared placement metadata and slot order | One-to-six plants remain grounded, collision-free, and depth ordered in both the dashboard and home widget; missing artwork keeps a named stage-appropriate fallback. |
| Plant stage/growth | Plant growth points | The plant card shows stage progress in full words, plain-language plant health, the next stage, and a proportional progress bar; flowering/rare states show fully grown. |
| Plant interaction | Stable plant ID plus responsive painted bounds | Generous hit area, pointer cue, hover preview, click-to-pin, empty-scene/Escape dismissal, and arrow-key navigation. |
| Nurtured plant | Valid `focus_plant_id` | An attached Nurturing badge identifies it in both scenes; it receives 80% of future growth and invalid IDs repair to the first slot. |
| Garden milestone | Total reviews plus persistent pending reward | Home shows progress/readiness; dashboard offers up to three stable unowned species and claims one slot at a time. |
| Plant story | Stable plant ID plus semantic milestone memories | View story opens a keyboard-accessible detail dialog with generated/editable name, planted date, current growth, and newest-first warm factual timeline. |
| Quest progress | Daily quest metric | Preserved through same-day restart; regenerated only at rollover. |
| Appearance | Anki add-on config | Saved explicitly, applied to preview/dashboard, and restored on restart. |
| Responsive layout | Available dialog/webview geometry | Dashboard controls stack instead of clipping; home metrics collapse to one column; cards and overlays remain inside unusually small scenes. |

Strict acceptance requires Deck Browser, Overview, dashboard, persisted state, and Anki's own studied-today count to agree after a real review.

The former bottom roster is intentionally removed. Plant data has one authoritative presentation in the interactive scene rather than a duplicated dashboard section.
