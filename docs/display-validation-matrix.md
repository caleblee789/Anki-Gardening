# Display validation matrix

| Surface value | Authoritative source | Presentation contract |
|---|---|---|
| Nurtured-plant Growth | `active_plant_id` plus the selected plant's Growth/stage display | Home and the compact Garden strip show the current nurtured plant's progress. If no unfinished plant is being nurtured, they explain that Growth is waiting rather than substituting a garden-wide total. |
| Anki streak | `streak_days` plus `STREAK_BONUS_TIERS` | Shows consecutive Anki days, the current Growth bonus, and the next threshold where space permits. |
| Garden Coins | Internal `currency_balance` plus the transaction ledger | Learner-facing UI consistently says Garden Coins. Recent credits and spends, including the resulting balance, live in Progress rather than the permanent strip. |
| Card answers and Growth today | Schema 14 `daily_stats.reviewed`, `base_growth`, `streak_bonus_growth`, `fertilizer_growth`, `bonus_growth`, and `growth_earned` plus the scheduler-day processed-ID ledger | Counts each supported answer event once, including repeat answers and late lower-ID sync rows. The detailed breakdown appears only under Progress. |
| All-due status | Once-per-Anki-day flag granted by live due evaluation | Today explains the included/excluded obligation contract and the +10 Garden Coin reward. |
| Nursery counts | `catalog_summary()` and the user's collection | Shows dynamic text such as “2 plants collected. 1 plant available now.”; never a hard-coded roster denominator. |
| Nursery stock | Complete release-preferred Verdant Twilight V6 assets for every stage, valid geometry-v2 placement metadata, and `direct_soil` compatibility | Only complete lines appear for starter selection or purchase. Bonsai, Rose, Sunflower, Lavender, Hydrangea, Peony, Foxglove, Japanese Maple, Wisteria, and Dahlia satisfy the current bundled contract; retired or incomplete lines remain hidden without affecting an already-owned plant. |
| Garden spaces | `unlocked_slots`, planted slots, and space price tables | Two spaces begin unlocked; up to six direct-soil spaces can be used. Nursery presents only the next valid space unlock. |
| Plant composition | `verdant_twilight_surface_v6`, six named support lines/contact planes, and depth-sorted placements | One to six plants remain grounded across supported full-Garden and home aspect ratios. Home uses the same art but exposes no scene interaction. |
| Nursery landmark | Registered `garden.nursery.open` action copy plus manifest landmark geometry | Full Garden provides restrained hover/focus glow, **Open Nursery** tooltip, and click/Enter/Space activation. Move mode disables it; home omits it. |
| Default, hover, and selected plant | `PlantInteractionState` plus geometry-v2 `interaction_bounds` | Default has no emphasis; hover/focus is restrained; selection is stronger and persistent. No scale or bounce is used. |
| Selected plant | Selected scene payload and `growth_display()` | Compact card shows identity, stage, stage-local Growth, approximate answers remaining, Fertilizer status, and four stable actions: Nurture, Fertilize, Move, Story. |
| Move state | `PlacementDraft`, valid destination slots, and the committed placement change | Scene highlights valid spaces. Selecting a space commits a move or swap immediately; Escape/Cancel exits before placement, save failure rolls back, and Undo restores the last committed arrangement. No destination dropdown or Done action is shown. |
| Fertilizer choice | Fertilizer specification table, plant Fertilizer, real clock, and `currency_balance` | Choice cards show tier, Garden Coin cost, direct Growth per answer, and duration. Replacement confirmation explains that remaining time will be discarded. |
| Plant Story | Stable plant ID plus semantic memories | Hero shows identity and current Growth, edit is inline, memories are oldest to newest, and **Up next** describes the next known milestone. |
| Settings | Whitelisted Anki config plus staged settings payload | Verdant Twilight is a read-only theme card. Garden display and Motion are primary; Fine tune is collapsed; the live preview updates before Save. Cancel restores persisted values, and Restore defaults only stages them. |
| Responsive layout | Available dialog/webview geometry | Pages scroll vertically, Settings stacks at the compact breakpoint, cards remain onscreen, and no horizontal scrolling is required. |

Strict runtime acceptance compares Deck Browser, Overview, the full Garden,
selected-plant card, Nursery, Story, Settings, schema 14 JSON, and Anki's own
studied-today result after real reviews.
