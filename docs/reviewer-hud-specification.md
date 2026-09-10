# Reviewer and reward UI specification

The HUD and receipts render committed engine projections. Growth, Coins, Finds, inventory, completion, scheduling, and sync mechanics remain authoritative in the engine. The live HUD and finalized session summary share one session accumulator.

## Expanded review HUD

1. Text-only Anki Garden title, Coin balance, and collapse control.
2. Active plant name, artwork, and progress.
3. Three equal-width **Coins / Growth / Discoveries** boxes under “This session”, directly below the plant.
4. Current reward, then Recent rewards, inside the existing HUD.

The Today’s cards bar, completed/remaining counts, and Next card Growth row are absent. The expanded shell stays 296 px wide, content-fitted, inside Anki’s navigation and answer-control safe area. “This session” is brighter and semibold at its unchanged 12 px size. The totals row appears after the first earned result, displays all three categories (including zeros), and retains its history chevron. Long totals abbreviate within their own box; the exact value is available in the tooltip and committed records. The boxes never wrap into separate rows or enlarge the HUD.

The existing plant art composition and checkpoint semantics remain intact. Assets use alpha-aware sizing, correct stage imagery, and restrained ground shading. The progress track shows checkpoints within the current growth stage; “Next” names the next plant stage. Full Bloom remains the player-facing label for the persisted `rare` plant stage.

## Compact review HUD

One vertical rail contains the plant/progress circle and one reward slot below it. No detached reward HUD, toast, automatic expansion, or separate history window appears.

| State | Logical size |
|---|---|
| Idle | 80 × 48 px |
| Coins or Growth | 80 × 70 px |
| Stored or Shared Growth | 80 × 86 px |
| Item, discovery, or milestone | 80 × 115 px |

The circle stays anchored. Bottom padding is 5–7 px. Coins/Growth use one icon-and-amount row, with no redundant resource caption. Stored and Shared each use one short line. Milestones use 32 px artwork and deliberate two-line captions, such as “Full Bloom / Reached”. Fonts retain the established compact scale; long totals abbreviate instead of clipping or adding lines.

The compact rail acknowledges committed Growth first, followed by plant milestones and discoveries/Finds/items, then Coins. Compact progress updates begin without waiting for the expanded reward dock's reveal delay. A new answer merges into visible Growth or replaces an already displayed Coin message immediately; an already visible milestone retains its reading time. Routine amounts coalesce without losing totals. Every original event remains in history. A bundle cannot archive during its inline sequence. Expanding pauses the sequence; collapsing resumes it. Remount restores the current frame, queued frames, and remaining hold without replay.

## Shared rarity and artwork treatment

| Reward | Accent |
|---|---|
| Rare | Gold `#E8C568` |
| Very Rare | Lavender `#CBB2F4` |
| Exceptional / Ultra Rare | Pearl pink `#EFB9DB` |
| Full Bloom | Gold `#E8C568` |

Rarity comes from committed event metadata or the reward catalog. A consolidated inventory reward preserves its source Find rarity. Titles, badges, and indicators use the same mapping in the expanded HUD, compact HUD, session summary, and sync receipt.

Both HUD sizes use one finite attention pulse when a notable drop arrives: approximately 480 ms compact or 650 ms expanded. **The glow behind the item exists only during that pulse and clears completely afterward.** The colored text, badge, and subtle indicator remain. Session-summary artwork has no persistent glow. Reduced motion suppresses the pulse. Opening details, reopening history, remounting, and repeated event IDs cannot replay it.

Reward cards use a short eyebrow, a rarity badge, clear artwork, and the item’s name. Discoveries show “NEW DISCOVERY” and the name once; there is no duplicate “Discovery” subtitle or “discovered” suffix. Finds use “GARDEN FIND”. Keep actual reward amounts or granted-item names where they add information. Avoid repeating category or backend source labels.

## Session summary

The 400 px, nonmodal summary shows three horizontal **Coins / Growth / Discoveries** boxes first, followed by the session’s studied-card count and earned rewards. The Today’s cards bar is absent.

Reward details remain visible. There is no expand/collapse control for the reward details or plants affected. Milestones and discoveries use the HUD’s card treatment; earned inventory and Find rows use the same badge, colors, artwork alignment, and concise copy. A Find is not repeated in the highlights when its earned-item row already represents it.

Growth distribution, affected plants, checkpoint details, Coin sources, and active consumables appear as naturally sized sections when relevant. The top metric boxes own the totals, so the details do not repeat “Total applied”, “Total earned”, or “Included in the session total” on every row. Long names wrap, quantities remain aligned, and item rows have no fixed-height clipping.

Discoveries means committed Garden Finds plus new Garden unlocks. An item granted by a Find is not counted again. Zero categories remain visible so the box order is stable. The underlying typed event streams remain separate.

The body alone scrolls when needed, with header and actions visible. The shell fits content up to 520 px and respects measured Home/Anki control clearances. Session and sync summaries remain mutually exclusive through the existing coordinator. Closing or continuing review restores focus correctly.

## Sync summary

The sync receipt uses the same text-only header, three equal-width Coins / Growth / Discoveries boxes, shared resource icons, reward cards, rarity badges, and actions as the session summary. The synced-review count follows the boxes. Discoveries combines committed Find quantities and Garden unlocks, with no duplicate counting of granted inventory.

Keep one Reward details control for the sync receipt's additional plant allocations and current boosts. This preserves its existing progressive disclosure. Discoveries use NEW DISCOVERY and their name once; Finds use GARDEN FIND and their canonical artwork. Full Bloom uses the same gold title and rounded indicator treatment in either state. Transparent item images remain clear, and scenery thumbnails render at the display's pixel density.

All three headers omit the former Growth logo. Coin, Growth, and Discovery icons beside values remain. The session entrance is one 200 ms fade that clears its graphics effect at completion; layout-managed children never move during the animation.

## Verification and handoff

Use existing checks and focused native rendering. Do not create a broad new test or accessibility matrix for this presentation work. Check actual text bounds, art clarity, three-box alignment, removed daily bars, fixed-open details, event priority, rapid reward aggregation, and pause/remount continuity.

The current capture contract is v29: 51 full-profile surfaces across five contact sheets, with 22 representative surfaces. This lane owns the seven Sheet 5 integration/reward surfaces. Its focused captures and 35-frame reward gallery do not imply combined five-sheet release approval. Current evidence and implementation details are recorded in [the Sheet 5 handoff](ui/reviewer-release-polish-20260905.md).
