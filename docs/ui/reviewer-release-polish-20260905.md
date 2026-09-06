# Sheet 5: review, session, and sync UI handoff

The seven integration and reward surfaces have been implemented in the shared working tree. This handoff records the accepted design, affected files, and evidence for the other four UI lanes. It does not publish or approve the combined add-on release.

## Implemented surfaces

| Contact-sheet surface | Result |
|---|---|
| 45. Active Deck Browser Home After Nurture | Concise Garden entry copy, clear Open garden action, improved contrast, and bounded placement beside transient summaries. |
| 46. Reviewer HUD Expanded | Text-only title, preserved Coin balance and collapse control, stage-correct plant art, current-stage progress, then This session and three equal totals boxes above rewards. Removed Today's cards and Next card Growth rows. |
| 47. Workspace Reviewer Collapsed | One compact vertical rail; rewards appear inside it below the plant/progress circle. No detached reward popup or automatic expansion. |
| 48. Reviewer Reward Dock Bundle | Prioritized committed rewards, matching rarity badges and art, finite attention pulses, and usable detail/history controls inside the existing HUD. |
| 49. Workspace Reviewer Rewards List | Concise, named reward history with exact amounts; routine Growth remains distinguishable without raw backend copy. |
| 50. Session Summary After Review | Text-only title, Coins/Growth/Discoveries boxes first, session review count, shared discovery/Find cards, permanently visible reward details, and fixed actions outside the scrolling body. |
| 51. Sync Rewards Summary | Text-only title and the same three totals boxes, resource icons, rarity cards, artwork treatment, and actions. Synced-review copy remains specific to its source; one existing disclosure exposes additional sync detail. |

## Compact spacing and rewarding feedback

The rail is 80 px wide. It is 48 px tall at rest, 70 px for Coins/Growth, 86 px for Stored/Shared Growth, and 115 px for an item or milestone. Bottom padding measures 5–7 px. A resource icon and amount share one line; redundant Coins/Growth captions are gone. Stored and Shared each occupy one short line. Full Bloom uses 32 px art and the deliberate two-line caption “Full Bloom / Reached”. Large values abbreviate without clipping, with exact values retained in tooltips and history. Font sizes were not increased.

Major milestones and discoveries/Finds/items precede Coin and Growth amounts. Rewards advance sequentially in the same slot. Routine amounts coalesce without loss. Expanding pauses the sequence; collapsing or remounting restores its position and remaining hold. Duplicate committed IDs do not replay rewards. Every earned event remains in history.

Rare rewards use gold (#E8C568), Very Rare lavender (#CBB2F4), and Exceptional/Ultra Rare pearl pink (#EFB9DB). Full Bloom remains gold. The mapping is shared by all four reward presentations. The expanded and compact HUDs pulse briefly on a notable drop; glow behind artwork exists only during that pulse and fully clears afterward. No standing art glow obscures the item. Reduced-motion settings suppress the pulse.

## Shared layout and meaning

Coins, Growth, and Discoveries always have the same order. Discoveries counts committed Garden Finds plus new Garden unlocks; inventory granted by a Find is not counted again. Session and review share the session accumulator; sync uses its own committed batch, so their totals need not be numerically identical. No reward, economy, scheduling, or sync rules are recomputed by these UI changes.

The review totals sit directly beneath the plant and above current/recent rewards. “This session” is brighter and semibold at the existing 12 px size. The progress track still shows checkpoints within the current stage; Next names the destination stage.

Discovery cards show NEW DISCOVERY, a rarity badge, artwork, and the item name once. They omit the redundant Discovery subtitle and discovered suffix. Finds show GARDEN FIND. A consolidated earned-item row retains its source Find rarity and name. Session details do not repeat their own totals or re-list the same Find as a second highlight.

Only the summary body scrolls. Header and actions remain visible, long names wrap naturally, and quantity columns remain aligned. The session entrance now fades the body once and clears its graphics effect, avoiding misplaced layout-managed children and the large gaps seen in earlier native captures. Retained plant artwork is preserved when current plant state is unavailable. Sync Find artwork resolves from the canonical catalog, and its environment thumbnails use display-density rendering.

## Discovery resource asset

A tiny painted mint-and-gold discovery spark now accompanies Discoveries totals, matching the Coin and Growth resource assets. Its RGBA source is retained at [garden_discovery.png](../../artwork_source/ui/rewards/garden_discovery.png); the runtime [WebP](../../ankigarden/assets/v6_storybook_gouache/ui/garden_discovery.webp) is 256 × 256 and 18,220 bytes. [Generation provenance](../../artwork_source/ui/rewards/garden_discovery-generation.json) records the exact prompt and built-in image generation tool. Resizing and WebP encoding preserve the original colors and transparency. The asset manifest, shared icon mapping, and existing asset-count audit include it.

## Evidence

All seven selected surfaces passed their native per-surface checks and were visually inspected: six from native-09 and the expanded HUD retake from native-11. [Original native views](../../build/sheet5-implementation-20260905-223215/native-views.html) and [selected evidence](../../build/sheet5-implementation-20260905-223215/selected-surface-evidence.json) retain the exact PNG, manifest, and report paths. Both derivatives match the same production archive across 331 shared payload entries. The isolated processes exited gracefully with code 0.

Production SHA-256: `e222eae03ec946ec2936a65ca9a08d60d75f528107c52bfd71637fb20e502220`. Native-09 capture SHA-256: `80d8238295841866c36a3ee67592c9c6ae5f68a660813d754c9bd11fb3f6aca3`. Native-11 capture SHA-256: `5d5a20e6cd4d21e1fa38ebae9723619ec774eb0f5691c2500ce5bf30ddac6528`.

The expanded HUD retake fixes a capture-only sampling issue: the compacted expanded HUD was too sparse in the full-window sample grid. The final check measures the HUD's own image while retaining exact overlay-pixel, real-card DOM, geometry, and window-identity gates. Earlier failures are retained; they are not silently replaced or marked passed.

The final affected suite passed **370 existing tests, with 2 skipped**. Asset auditing passed, including 20 UI assets. After native capture, a parallel lane added bounded HUD image caches, optimized plant-choice lookup, and avoided an unnecessary thumbnail load. Those edits were preserved and reviewed. **All 21 settled Qt preview images were byte-identical before and after those changes**, and the existing suite passed again. Native archive provenance remains tied to the frozen pre-cache package, so the combined release must still be rebuilt after integration.

These focused reports retain a failed full-profile gate for the unrequested four-state dialog-scroll matrix. No full-profile release acceptance or final five-sheet contact set is claimed. The seven selected UI surfaces have no remaining observed clipping or layout failures in this evidence.

Focused Qt evidence includes [all 35 compact previews](../../build/sheet5-implementation-20260905-223215/reward-previews/index.html), [four rarity tiers](../../build/sheet5-implementation-20260905-223215/rarity-previews/index.html), and [session/sync receipts](../../build/sheet5-implementation-20260905-223215/receipt-previews/index.html). These exercise actual Qt widgets and production artwork. Temporary checks cover text bounds, minimal bottom space, reward priority, coalescing, duplicates, pause/resume/remount, finite pulses, rich animated summary scrolling, and three-box alignment. Existing tests are reused; no new test file or accessibility testing matrix was added.

## Integration ownership

Presentation lives in reviewer_hud_widget.py, collapsed_reward_feedback.py, reward_rarity.py, reward_receipt.py, session_summary_card.py, sync_reward_summary.py, and home_widget.py. Hooks/reviewer and reviewer_hud carry projection and remount integration. garden_asset_thumbnail.py changes only environment pixel-density rendering, which also improves its other consumers. icons.py and the asset manifest register the Discovery icon. Capture runtime and validators follow the accepted layout and count semantics. The [reviewer specification](../reviewer-hud-specification.md) is the continuing design contract.

Preserve unrelated dirty files and the other lanes' work. Rebuild the combined archive after integration and use the current v29 inventory, with 51 full-profile surfaces across five sheets. This lane's focused evidence does not replace the other four sheets, their mechanics work, or human acceptance of the combined release.
