The latest manifest identifies a complete Anki Garden 2.1.0 capture set with five pages and 34 surfaces. It also specifies that the cream areas are contact-sheet padding outside the captured application UI.  Automated checks currently pass, but visual review remains pending. 

Use the following as the Codex goal prompt:

```text
# Goal: Complete Anki Garden UI release-readiness audit, remediation, and verification

Perform a complete implementation pass that brings every Anki Garden UI surface in the latest full contact-sheet capture set to release quality.

This is not an analysis-only task. You must:

1. Analyze the entire contact-sheet set.
2. Identify every release-readiness problem.
3. Implement all necessary corrections.
4. Regenerate the complete contact-sheet set.
5. Review the newly generated set in its entirety.
6. Batch-fix all remaining problems.
7. Repeat the full regeneration and review cycle until the UI satisfies every release criterion below.

The current full capture contains five contact-sheet pages and 34 UI surfaces. Use the current manifest as the canonical inventory if the exact count changes.

## Critical interpretation rule

The cream-colored area surrounding captured surfaces is contact-sheet padding outside the application UI.

Do not:

- Treat cream padding as application whitespace.
- Expand dialogs, cards, dashboards, or other surfaces to fill cream padding.
- Change application sizing based on the amount of cream visible.
- Modify the contact-sheet assembler merely to hide application defects.
- crop out actual UI defects during contact-sheet assembly.

Evaluate whitespace only inside the actual captured UI boundaries.

# Required working method

## 1. Audit the complete set before making changes

Before editing code, inspect all five contact sheets and every individual surface at a readable scale. Open the native surface captures when the contact-sheet overview is too small to evaluate accurately.

Do not audit only the most visibly problematic screens. Review every surface, including screens that initially appear acceptable.

Create an internal issue ledger with at least:

- Contact-sheet page
- Surface number and name
- Visible problem
- Severity
- Likely root cause
- Shared component or code path involved
- Other surfaces that may use the same component
- Planned correction
- Verification method

Identify relationships between surfaces, including:

- The same shared dialog shell
- The same tabs or navigation
- The same item or plant appearing in multiple locations
- Sequential purchase or reward flows
- Shared asset mappings
- Shared progress calculations
- Shared status chips
- Shared buttons and icons
- Reviewer and Anki home integrations
- Collection, Nursery, Settings, Progress, and Garden representations of the same state

Do not begin contact-sheet regeneration during this audit.

## 2. Consolidate defects by root cause

Before implementing, group issues that arise from the same root cause.

Examples:

- A shared dialog body causing clipping on several screens
- A fixed-height shell causing unnecessary internal blank space
- One incorrect asset lookup affecting multiple item representations
- One stage-model inconsistency affecting Garden, Progress, Plant Story, and reviewer HUD
- One button component causing inconsistent sizing or disabled-state appearance
- One progress-bar implementation producing incorrect fill widths
- One scroll container allowing scrollbars to overlap tabs
- One stale terminology source affecting several dialogs

Prefer shared component, shared state, shared styling, and shared asset-mapping corrections over screenshot-specific patches.

Do not hardcode offsets or dimensions for a single screenshot when the underlying component can be fixed correctly.

## 3. Finish the entire planned implementation batch before regenerating

This is a non-negotiable workflow requirement.

After auditing the current contact-sheet set:

1. Finalize the complete issue ledger for that iteration.
2. Plan all changes needed across all five sheets.
3. Implement every planned correction.
4. Recheck all shared-component consumers.
5. Run preflight checks.
6. Only then regenerate the complete contact-sheet set.

Do not regenerate contact sheets:

- After each individual fix
- After each surface
- After each contact-sheet page
- Merely to check a minor spacing change
- Before all currently known issues have been addressed
- As the primary debugging mechanism for ordinary code errors

Use code inspection, DOM inspection, component-level checks, existing automated checks, and targeted runtime inspection during implementation.

A full contact-sheet regeneration should represent a complete remediation batch, not one incremental edit.

If a new code-level issue is discovered while implementing the batch, add it to the same batch and correct it before regeneration whenever practical.

# Full visual audit requirements

Evaluate all of the following categories on every applicable surface.

## A. Clipping and containment

There must be no:

- Clipped text
- Cropped icons
- Truncated buttons
- Partially hidden status chips
- Cut-off dropdowns or menus
- Footer actions outside their dialog
- Progress bars touching or entering card borders
- Content extending behind a scrollbar
- Controls extending beyond a card or viewport
- Artwork cut off unintentionally
- Tooltips, popovers, or menus leaving the visible application viewport
- Text hidden because of fixed line heights
- Titles colliding with close controls
- Long labels pushing actions offscreen
- Last rows partially hidden at maximum scroll

Check bounding boxes, not only visual appearance.

Use appropriate combinations of:

- `min-width: 0`
- `min-height: 0`
- `box-sizing: border-box`
- content-derived sizing
- bounded text wrapping
- ellipsis only where appropriate
- stable action columns
- adequate scrollbar clearance
- adequate bottom padding
- popover collision handling

Do not solve clipping by unnecessarily shrinking all text or removing useful information.

## B. Scrolling behavior

Every scrollbar must be intentional.

There must be:

- No horizontal scrolling at the tested dimensions
- No scrollbar when all content fits
- No scrollbar caused by one- or two-pixel overflow
- No scrollbar entering a fixed header, title, or tab row
- No nested scrolling unless the interaction clearly requires it
- No full-dialog scrolling when only the body should scroll
- No fixed footer that scrolls out of view
- No final item hidden behind a footer
- No scrollbar obscuring card text or controls
- No empty oversized scrolling region beneath short content

Preferred dialog structure:

- Fixed header
- Fixed tab row when present
- One scrollable body
- Fixed footer when present

Use content-derived dialog heights for sparse screens. Apply maximum heights only when needed to keep a dialog within the available screen.

Do not leave large internal blank regions merely to keep every tab or state at the same fixed height.

## C. Media, artwork, SVGs, and icons

Every item, plant, reward, fertilizer, booster, decoration, scenery, achievement, stage, currency, warning, lock, and completion state must display the correct media everywhere it appears.

Audit the canonical mapping between logical IDs and media assets.

Verify:

- Every required image exists
- Every required SVG exists
- Every image and SVG loads successfully
- No broken image placeholder appears
- No required asset silently renders as an empty box
- No location uses a generic placeholder while another location has the correct asset
- No item displays another item's artwork
- No icon depends on a missing Unicode or icon-font glyph
- SVG view boxes are valid
- SVG strokes and fills remain visible on the dark background
- Artwork aspect ratios are preserved
- Artwork is not blurred from excessive scaling
- Transparent padding does not cause incorrect centering
- Plant scene artwork uses correct soil anchors
- Thumbnail and scene versions use appropriate context-specific sizing
- Locks, warnings, close controls, completion icons, menu icons, and currency symbols are visually consistent

When an item appears in the Nursery, purchase dialog, success dialog, reviewer HUD, session summary, sync summary, collection, or Garden scene, all representations must resolve from the same canonical item definition.

Do not independently hardcode asset paths in each surface.

If an item currently has media in one location but not another:

1. Identify the canonical item or asset record.
2. Add or correct the required context mapping.
3. Use the canonical shared media component in every location.
4. Verify every appearance of that item in the regenerated set.

Do not use emoji as a substitute for a missing product asset.

## D. Layout, density, and whitespace

Review all application-internal spacing.

Correct:

- Unnecessarily tall dialogs
- Large empty body regions caused by fixed heights
- Excessive padding around sparse content
- Cards with inconsistent internal padding
- Uneven column widths
- Misaligned labels and values
- Actions floating far from their associated content
- Buttons consuming disproportionate space
- Controls pressed against borders
- Crowded title bars
- Inconsistent gaps between repeated rows
- Unbalanced two-column layouts
- Large unused areas that could be eliminated through content-derived sizing

Preserve deliberate visual breathing room. Do not compress the interface until it becomes dense or difficult to scan.

Use a shared spacing scale and consistent component dimensions instead of arbitrary margins.

## E. Color and visual hierarchy

Verify that color communicates consistent meaning.

Use stable semantic roles:

- Mint or primary green: primary actions, selected states, positive progress
- Gold: Garden Coins and explicit reward value
- Amber: warnings and value-loss confirmations
- Coral or red: destructive actions and shortages
- Purple or another distinct rare color: rare discoveries or special milestones
- Neutral green: ordinary statuses and surfaces

Correct cases where:

- A stage chip looks like currency
- A warning looks like a reward
- A status looks like a clickable button
- A disabled button disappears into the background
- Selected, hovered, completed, equipped, nurtured, active, and locked states look identical
- Adjacent dark surfaces cannot be visually distinguished
- Text contrast is insufficient at the current macOS 100 percent text setting

Keep colors consistent across every surface.

## F. Typography and text organization

Verify:

- Consistent heading sizes
- Consistent body sizes
- Consistent secondary-text sizes
- Consistent capitalization
- Consistent punctuation
- Correct singular and plural forms
- No labels wrapping unnecessarily
- No metadata competing with primary information
- No excessive duplicate wording
- No text that refers to removed or renamed systems
- No terminology that changes between surfaces
- Long plant or item names have defined wrapping or truncation behavior
- Numeric columns use tabular numerals where appropriate

Use sentence case consistently unless a product name requires otherwise.

Do not reduce important text below a comfortably readable size merely to avoid fixing layout.

## G. Buttons, links, chips, and controls

Every interactive element must look interactive. Every noninteractive status must not look like a button.

Audit:

- Primary buttons
- Secondary buttons
- Tertiary actions
- Destructive actions
- Disabled controls
- Loading controls
- Status chips
- Tabs
- Segmented controls
- Switches
- Text inputs
- Dropdowns
- Icon buttons
- Overflow menus
- Disclosure controls

Requirements:

- Consistent heights and padding
- Stable alignment
- Visible hover and pressed states where applicable
- Clear disabled states
- No invisible hit targets
- No plain text used as the only affordance for an important action
- No status chip with misleading hover or pressed styling
- No active state represented as an action that can be selected again
- Visible switch thumbs in both on and off states
- Close controls must be complete, centered, and consistently sized
- Buttons must not wrap at the captured dimensions
- Loading states must prevent duplicate transactions

## H. Data and state correctness

Every number and state shown in the UI must reflect the actual fixture or engine state.

Audit:

- Progress numerators and denominators
- Progress-bar fill percentages
- Garden Coin balances
- Projected purchase balances
- Inventory before and after values
- Growth before and after values
- Remaining charge counts
- Stage transitions
- Reward subtotals and totals
- Completed and remaining card counts
- Achievement dates
- Streak values
- Item ownership
- Equipped, active, displayed, queued, nurtured, and locked statuses
- Find limits and daily counts
- Session-only totals versus daily totals
- Synced rewards versus local-session rewards

Do not display a nonzero progress fill for a zero numerator.

Clamp progress values correctly:

`fill = clamp(numerator / denominator, 0, 1)`

Do not show impossible dates, stale milestones, contradictory stage names, or a checkpoint belonging to a prior stage after a stage transition.

Do not alter gameplay balance merely to make a screenshot appear consistent. Use the actual engine definitions as the source of truth, then correct the display or fixture.

## I. Cross-surface consistency

Search for contradictions across all surfaces.

The same concept must use the same:

- Name
- Capitalization
- Icon
- Artwork
- Stage model
- Reward name
- Currency terminology
- Collection terminology
- Button semantics
- Status semantics
- Progress calculation
- Count definition
- Item category
- Plant display name
- Scenery or decoration terminology

Sequential flows must preserve the same object and state.

Examples that must reconcile:

- Selected starter species through placement
- Plant target through fertilizer purchase and queueing
- Plant target through growth-charge confirmation and success
- Balance before purchase, displayed price, and balance after purchase
- Inventory before and after purchase
- Growth added and resulting total
- Session reward components and total
- Sync reward components and total
- Today completed plus Today remaining
- Stage before, resulting stage, and next-stage progress
- Collection species totals across Progress, Nursery, and purchase success
- Active decoration or scenery across Settings, Garden Appearance, Today’s Cards, Session Summary, and reviewer UI

Independent contact-sheet scenarios may intentionally use different fixture states. Sequential surfaces within the same scenario may not contradict each other.

Use explicit capture fixture or scenario identifiers internally when needed to distinguish independent states.

## J. Host integration

Anki Garden must coexist cleanly with the Anki host interface.

Verify that:

- The Anki home card does not move or cover the deck table
- The home card does not attempt to fill unrelated Anki whitespace
- Reviewer HUDs do not cover card content unnecessarily
- Reviewer HUDs do not cover Show Answer or answer buttons
- Reviewer HUDs do not cover Edit, More, or footer controls
- Reward notifications remain inside a defined reviewer safe area
- Popovers and dialogs appear above the HUD
- The HUD collapses or adapts when vertical space is insufficient
- Anki navigation and footer elements do not shift unexpectedly
- Session and sync summaries do not open simultaneously unless intentionally supported
- Modal surfaces have a clear focus model and appropriate scrim
- Nonmodal surfaces do not appear visually modal

## K. Runtime quality

During the capture sequence, verify there are no:

- JavaScript errors
- Python exceptions
- Missing file errors
- Failed SVG or image loads
- Repeated event-handler execution
- Duplicate purchases
- Duplicate reward notifications
- Stale state after closing and reopening a dialog
- Focus traps
- Dead buttons
- Unhandled empty states
- Console warnings caused by invalid layout or assets

# Implementation requirements

## Shared fixes first

Prioritize shared primitives before surface-specific CSS.

Likely shared targets include:

- Dialog shell
- Dialog sizing
- Scroll body
- Header and footer
- Tab bar
- Button component
- Status chip
- Switch
- Currency display
- Progress bar
- Catalog card
- Completion state
- Plant stage strip
- Plant artwork renderer
- Item artwork resolver
- Reviewer HUD container
- Reward notification stack
- Popover positioning
- Empty-state component

After changing a shared component, inspect every surface that uses it.

## Preserve product behavior

Do not change gameplay, progression, economy, reward amounts, or unlock rules unless the current source code and fixtures demonstrably contradict the intended engine behavior.

The task is release UI readiness, including correct state wiring and correct presentation.

## Avoid screenshot-specific hacks

Do not:

- Position elements using coordinates copied from one screenshot
- Add fixed heights solely to match one capture
- Hide overflowing content to make a defect less visible
- Remove necessary information instead of organizing it correctly
- Crop media to conceal an asset problem
- Add arbitrary delays only to make the capture pass
- Modify contact-sheet padding to conceal layout issues
- Duplicate components to avoid fixing the shared implementation

# Testing requirements

Use the existing automated test and capture infrastructure whenever possible.

Do not create an unnecessarily large test suite.

Add a new test only when it protects a meaningful release invariant that is not already covered, such as:

- A shared geometry or overflow rule
- A canonical asset mapping
- A sequential transaction invariant
- A progress calculation
- A reward reconciliation
- A stage-transition calculation
- A shared component that previously caused defects in multiple surfaces
- A reviewer safe-area boundary
- An item ID resolving to the correct artwork

Prefer one focused test for a root cause over one test for every affected screenshot.

Appropriate lightweight checks include:

- DOM geometry assertions
- Asset existence and mapping validation
- Progress fraction assertions
- Balance and inventory reconciliation
- Sequential fixture-state validation
- Capture completeness validation
- Console error detection

Do not add:

- Broad speculative platform matrices
- A test for every individual margin or color value
- Pixel-perfect tests for every surface
- Redundant tests already covered by the existing capture suite
- Large combinations of states that are not relevant to release
- New capture surfaces solely because a theoretical state could exist
- Windows or Linux visual testing for this pass
- Enlarged text-scaling test matrices for this pass

The required visual environment for this release pass is:

- macOS
- 100 percent text scaling
- Current capture dimensions
- Current Anki host layout used by the full capture profile

# Pre-regeneration checklist

Before each full contact-sheet regeneration:

1. Complete every planned code and asset change for the current iteration.
2. Confirm all affected shared components have been reviewed.
3. Run existing relevant automated checks.
4. Run only the new targeted tests justified by actual defects.
5. Confirm the application starts without errors.
6. Confirm all referenced media files resolve.
7. Confirm no known issue remains intentionally deferred within the current iteration.
8. Confirm capture fixtures and scenario data are internally consistent.
9. Confirm the complete capture sequence can run without manual intervention.

Do not regenerate while known planned fixes remain unimplemented.

# Full regeneration and review loop

After completing the full implementation batch:

1. Regenerate the entire full contact-sheet set in one run.
2. Confirm the generated manifest reports a complete capture.
3. Confirm every expected page and surface is present.
4. Confirm no capture is blank, duplicated, stale, or from an older package build.
5. Inspect all contact sheets again from the beginning.
6. Inspect native surface captures wherever necessary.
7. Compare the regenerated surfaces against the issue ledger.
8. Check for new regressions caused by shared changes.
9. Create a new complete issue ledger for any remaining defects.
10. Batch-fix every item in that new ledger.
11. Run preflight checks.
12. Regenerate the complete set once more.

Repeat this full-set cycle until all release criteria pass.

Do not regenerate only the page currently being fixed as the primary verification strategy. A change to a shared component can affect any of the five pages.

Targeted local previews may be used during debugging, but final verification for every iteration must be a complete full-profile contact-sheet generation.

# Definition of done

The UI is ready for release only when the final complete contact-sheet set demonstrates all of the following:

## Geometry

- No clipped text
- No clipped artwork
- No clipped icons
- No clipped buttons
- No overlapping content
- No offscreen actions
- No malformed close controls
- No menus or popovers leaving their valid viewport
- No content touching borders unintentionally
- No internal blank regions caused by incorrect fixed sizing

## Scrolling

- No horizontal scrolling
- No unintended vertical scrolling
- No scrollbar when content fits
- No scrollbar entering a header or tab row
- No nested scroll defect
- No clipped final list item
- Fixed headers and footers remain fixed where intended

## Media

- Every asset is present
- Every item uses the correct artwork
- Every context displays required media
- No broken media references
- No generic fallback where a real product asset exists
- No inconsistent SVG, icon, or artwork mapping
- No blurred or incorrectly anchored plant art
- No missing image in one UI location when the same item has an image elsewhere

## Consistency

- No contradictory stage model
- No contradictory counts
- No contradictory balances or inventory
- No contradictory plant target
- No contradictory equipped, active, displayed, or owned state
- No stale or inconsistent terminology
- No inconsistent capitalization
- No inconsistent reward naming
- No impossible dates
- No incorrect progress widths
- No stale prior-stage milestone after a stage transition

## Visual quality

- Clear information hierarchy
- Consistent spacing
- Consistent controls
- Appropriate content density
- Legible typography
- Clear selected and disabled states
- Stable semantic colors
- Attractive and coherent Garden presentation
- No obviously unfinished placeholder visuals

## Host integration

- No overlap with Anki navigation, card content, answer controls, or footer
- Home and reviewer surfaces remain proportionate to their purpose
- Modal and nonmodal behavior is visually clear
- Reviewer panels remain within their safe area

## Runtime

- Existing relevant automated checks pass
- Any justified targeted tests pass
- No console errors
- No missing media errors
- No duplicate transactions or notifications
- Final manifest is complete
- Every final contact sheet has been visually reviewed

# Final deliverables

When complete, provide:

1. The final regenerated full contact-sheet set.
2. The final generated manifest.
3. A concise summary of the shared components and systems changed.
4. A list of important surface-specific corrections.
5. A list of tests added or modified, with a one-line justification for each.
6. The number of complete contact-sheet regeneration cycles performed.
7. Confirmation that every final surface was reviewed.
8. Any remaining limitation, clearly identified.

There should be no unresolved release-blocking UI defects.

Do not stop after proposing a plan. Continue through implementation, full regeneration, complete visual review, batched correction, and final verification.
```
