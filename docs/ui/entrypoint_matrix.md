# Anki Garden UI entry points

The main window has four persistent tabs: **Garden**, **Collection**, **Shop**, and **Progress**. Opening a destination selects its existing page; it does not create a second catalog or progress window.

| Entry | Destination | Behavior |
| --- | --- | --- |
| Anki Home or Overview: Open Garden | Garden | Opens the scene or resumes starter selection and placement. |
| Garden tab | Garden scene | Keeps the compact nurtured-plant summary below the scene. Plant menus open only through explicit selection. |
| Plant hover / click | Plant highlight / floating menu | Hover highlights; click or Enter selects a plant and opens its anchored menu. Selection does not change nurturing. |
| Nurtured-plant bar: View plant | Nurtured plant's floating menu | Opens the current nurtured plant; repeated activation keeps the same menu open. |
| Nurtured-plant bar: Choose plant | Existing plant-selection flow | Appears when no plant is being nurtured. Inspecting a candidate does not start nurturing it. |
| Collection tab or cottage | Collection → Plants | Browse owned and undiscovered species; open a species or plant for details. |
| Collection → Scenery / Decorations | Owned appearance choices | Selecting artwork applies immediately. Undo restores the appearance; active and queued bonuses are separate. |
| Collection → Landmarks | Landmark progress and build list | Shows Stored Growth, build requirements, progress, and display choices. |
| Shop tab or greenhouse | Shop | Plants, Supplies, Scenery, and Decorations, using compact rows. |
| Progress tab | Progress | Today, Achievements, and Coins. The page is retained within the session. |
| Coin balance | Progress → Coins | Opens the transaction history. |
| Progress → Today | Daily progress | Combines Today’s Cards, earned Growth, Finds, streak calendar, and next bed unlock. Details contains secondary rules. |
| Plant menu: Nurture | Selected plant | Changes the nurtured plant through the existing engine action. Stop nurturing is under More. |
| Plant menu: Use item | Owned Fertilizer / Growth Charges | Keeps the selected plant as the target. Shop supplies carries that target into the Shop. |
| Plant menu: Move | Garden placement | Hides the menu during placement, highlights valid beds, and supports the existing Undo action. The menu returns after completion or cancellation. |
| Plant menu: Details | Plant details | Shows the individual plant, stage progress, name editing, and memories. Closing details preserves the menu selection. |
| Species tile | Species overview | Shows the species stages and owned instances. Undiscovered Full Bloom artwork stays hidden. |
| Settings gear or add-on settings menu | Settings | Garden name and display/reward preferences, with Save and Cancel. Diagnostics is collapsed. |
| Reviewer HUD | Garden / Shop and HUD collapse | Shows compact live progress without taking focus from Anki’s answer controls. |
| Session end / sync | Reward summary | Compact summary with Close, Open garden, and secondary Details. Closing a summary does not undo rewards. |
| Purchase / Growth Charge confirmation | Focused dialog | Displays the engine quote or outcome for the chosen item and target. Saving and spending remain engine-owned. |

The default Garden window is 1040 × 720, with an 860 × 580 minimum clamped to the available screen. Catalog and history pages scroll inside the window. Focused dialogs fit their content. Ordinary actions are 28–34 px high; artwork tiles are sized separately.

The nurtured-plant bar is approximately 72 px high, with 40 px artwork and a progress group bounded to 480 px. It is hidden during starter choice and initial placement. The floating menu prefers 304 px width, has content-driven height, and retains Close above a single scrolling content region in constrained viewports. Clicking the selected plant again, background click, Close, Escape, or leaving the Garden tab dismisses it. More and owned dialogs handle their own Escape first. Routine refreshes update an existing selection without opening a dismissed menu.

Capture contract v27 covers 18 representative and 36 full surfaces in two and five sheets. The v25/v26 contracts and historical captures remain preserved. Current Garden validation is recorded in the [plant-menu verification report](plant-menu-overhaul-20260904.md); the broader redesign history remains in [the redesign report](ui-redesign-2.2.0.md).
