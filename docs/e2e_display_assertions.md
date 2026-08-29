# End-to-end display assertions

Install the exact rebuilt `dist/anki_garden.ankiaddon` into a fresh, uniquely
named, disposable Anki 26.08 base/profile with sync disabled. Before any
interaction and again after restart, verify process identity, the unique
profile window, the disposable filesystem, and logged-out/sync-off state. Never
control the normal profile.

1. Launch cleanly with one **Caleb M. Add-ons Settings → Anki Garden settings** action, no direct **Tools → Anki Garden** action, and no add-on warning.
2. Confirm Deck Browser and Overview show the noninteractive named scene,
   nurtured plant, relative Growth, and **Open Garden**. Today’s Cards, Anki
   streak, Garden Coins, and achievements must remain in the full Garden and
   Garden Progress. Plant and Nursery clicks must do nothing there.
3. With fresh schema-25 state, choose **Open Garden**, verify the introduction,
   and proceed to the Starter Nursery. It must offer every release-ready species
   as a free starter and show no hard-coded collection denominator. Complete
   confirmation, placement, nurture, and completion; the other unlocked
   direct-soil space remains empty.
4. Before choosing a starter, complete a real card and verify study totals and the
   Anki streak advance while plant Growth and recurring rewards stay at zero.
   Choose and nurture a starter; confirm that earlier Growth and recurring
   rewards are not backfilled, while any reliably reconstructable one-time
   achievement is projected from authoritative history only once.
5. Confirm the Garden name is centered inside the themed frame. Activate Plant
   Growth, Anki streak, and Garden Coins by mouse and keyboard; verify each
   focused detail and its relative bar/rules. Header **Garden Progress** must
   open the six-page Today’s Cards, Plant Growth, Anki Streak, Garden Coins,
   Achievements, and Collection window, defaulting to Today’s Cards.
6. Hover and keyboard-focus Nursery and cottage. Confirm silhouette-following
   outlines, anchored labels, click/Enter/Space activation, and no empty-air
   rectangle. Confirm both targets are disabled while moving a plant.
7. In Nursery, verify **Plants**, **Fertilizers and boosts**, **Garden beds**,
   and **Garden Decorations and Scenery** tabs. Plant counts are data-driven;
   stage artwork is clear; Bonsai, Rose, Sunflower, Lavender, Hydrangea, Peony, Foxglove,
   Japanese Maple, Wisteria, and Dahlia are stocked by the current complete V6
   lines, while seeded legacy-owned species remain visible and usable.
8. Purchase, move to Collection, and plant in garden a species; unlock spaces
   three through six sequentially; purchase Small/Standard Growth Charges and
   use both; purchase a Garden Decoration and Scenery and confirm neither auto-activates.
   Confirm Grand shows no current acquisition path. For every Coin purchase,
   inspect artwork, item/category/quantity,
   exact mechanics, target where applicable, price, current/resulting balance,
   Cancel focus, disabled submission, and receipt. Exercise insufficient
   balance, persistence failure/retry, unavailable, already-owned, invalid
   target, stale price/balance, duplicate request, full garden, active-plant
   storage, and failed-save paths. No rejected operation may spend Garden Coins
   or lose Growth, Story, Fertilizer, Booster, inventory, or bed state.
9. Select plants at every scene edge and in intentional overlaps. Confirm one
   compact card, topmost-art hit testing, edge-safe placement, outside/Escape
    dismissal, and Nurture, Fertilize, Growth Charge, Move, Story in a stable
    order.
10. Select **Move** and choose a highlighted direct-soil space by mouse and
    keyboard. Confirm empty moves and occupied swaps save immediately, locked
    spaces reject, Escape/Cancel exits before placement, save failure restores
    the previous arrangement, and the temporary **Undo** action restores the
    last successful move. There is no destination dropdown or Done button.
11. Open Fertilize and verify Basic, Quality, and Magical cards show exact
    Garden Coin cost, Growth per card, one/two/four-hour duration, and labeled
    item art. Extend the same tier’s remaining wall-clock time, then queue a
    different tier without discarding either duration. Confirm the active and
    queued effects reflow cleanly at narrow and wide widths. Fill the five-dose
    limit; the next rejected dose must remain in inventory. Verify Fertilizer
    time continues outside the reviewer and transfers at Full Bloom. Seed a
    Booster Potion, use and extend it, and verify +5 stacks with Fertilizer for
    100 applicable cards.
    Select Herbalist’s Hourglass and Full Moon before the day’s locks, complete
    the first eligible answer, and verify a newly used Potion grants 150 cards.
12. Complete real Again and Good cards. Each eligible card gives the full 10
    base Growth plus displayed streak, Fertilizer, Booster, the locked Garden Bonus, and Scenery
    bonuses to the nurtured unfinished plant. Every other planted plant creates
    an exact 20% Shared Growth share. Verify a growing source receives its own
    share and a Full Bloom source divides its share among all planted plants
    still growing, including the nurtured plant. Switch with
    **Nurture** and verify old Growth never moves. Confirm Growth details
    reconcile requested, applied, redirected, Shared, Stored, Garden Decoration, Scenery,
    Growth Charge, and Instant Growth totals. Garden Find Instant Growth has no
    card modifier or Shared fan-out.
13. Cross 25/50/75/100 stage-local checkpoints and one stage threshold. Confirm
    concise image-led feedback, artwork transition, Garden Coin reason, and no
    disruptive modal. Exercise the Standard Find registry, rising protection,
    guaranteed next-card state, guaranteed Uncommon-or-better result, three-per-day
    cap, and pause/resume behavior. The full Garden may explain those mechanics;
    the persistent HUD shows a Find only as a committed reward reveal and never
    shows the cap, limit, protection state, or internal gap count. Independently exercise each environment tier's finite
    guarantee and all completion gifts. Confirm Standard and environment Finds
    can stack with predictable rewards, yet each stable card/pool identity is
    consumed once with no reroll. At Full Bloom, confirm overflow and remaining
    effects continue to the next planted unfinished plant or Stored Growth.
14. Exercise Today’s Cards with available New, Review, intraday
    learning/relearning, active filtered, suspended, and buried cards. Confirm
    exact inclusion, exclusions, new-to-learning continuity, repeated-answer
    stability, the at-least-one-eligible-card guard, one award, and no
    revocation. Verify in-progress copy emphasizes the global number left and
    completion becomes `All cards complete`, the exact Coin reward, and the
    scheduler-owned completed-card count. Waiting, ineligible, and unavailable engine states remain
    truthful and compact without exposing internal obligation names. In a
    maximized Anki window, verify the clean expanded right-docked HUD hugs its
    content, keeps its sticky header and session footer visible, wraps a long
    plant name, has no horizontal scroll, and leaves Anki’s review controls
    unobstructed. Commit six rewards from one answer and verify one integrated
    hero bundle, at most three secondary chips, a clear remainder action, no
    detached toast or X stack, and no replay after redraw, reload, or sync. Exit a continuous local session after at
    least one committed card and verify one upper-right, nonmodal **Session
    Summary** with `cards complete`, Today’s Cards start-to-exit state, exact
    local Growth, Garden Coins, Standard Finds, milestones/discoveries, and
    remaining effects. It must omit synced/background rewards, internal Find
    protection, zero rows, and any backdrop; the underlying Anki page remains
    usable.
15. Establish a clean desktop reconciliation boundary, then sync supported
    answers from both the current Anki day and earlier days. Include a delayed
    lower-ID answer after a higher one, distinct answer events for the same
    card, and a future/device-skew row. Every eligible answer introduced after
    the boundary applies exactly once regardless of day or ID ordering; only a
    cautiously proven current-day transition may award All Clear. Excluded rows
    create no Growth and are not consumed. Repeat the sync and simulate
    review-log, scheduler-cutoff, and save failure, then retry and confirm no
    completed card is lost or duplicated. Verify rewards and one centered,
    nonmodal Sync Rewards receipt commit together, survive a restart before
    successful mount, clear on that mount when presentation is enabled, and do
    not replay. Disable **Show rewards after syncing** and
    confirm reward processing continues without showing the receipt. Initial
    setup and one-way replacement must baseline without replaying history.
16. In the cottage's **Collection** page, inspect every shared exact mechanic,
    textual Equipped state, how-to-earn entry, locked silhouette, ordered odds,
    and deterministic progress to each environment guarantee. Before any
    progression action, change the displayed Garden Decoration, selected Garden
    Bonus, and Scenery freely. Confirm the displayed prop changes immediately.
    Complete the first eligible answer, then confirm Garden Bonus and Scenery
    changes queue for the next Anki day while displayed art may still change.
    In a separate fresh-day case, use a Growth Charge or consumable before
    answering and confirm it locks only Scenery; the Garden Bonus remains ready
    to change until the first eligible answer.
    Toggle each visual layer and confirm its passive still applies. Verify static
    Decorations only in Home and the native 3:2 scene using covered 4:3 source
    art; do not create a 16:9 or standalone 4:3 release route.
17. Open Plant Story and confirm enlarged actual-stage art, distinct editable
    name/species/stage labels, relative Growth bar, inline rename, oldest-to-newest
    timeline, warm early-story state, **Up next**, keyboard flow, rename
    persistence, and local date formatting.
18. Open Settings and confirm the read-only Verdant Twilight card and applicable
    Garden display/notification controls, with no duplicate garden preview.
    The persistent reviewer HUD is on by default through its own setting; the
    existing reviewer-reward setting controls active major dock reveals while
    the core plant projection and committed session footer remain available.
    **Show rewards after syncing** is on by default and controls only the
    nonmodal Sync Rewards receipt.
    Confirm Garden Decoration/Scenery selection, art quality/detail/performance,
    decoration animation, and Fine
    tune controls are absent; reduced motion remains automatic.
19. Stage settings and verify unsaved-state feedback updates immediately. Confirm
    Cancel restores persisted values, Restore defaults only stages values, Save
    settings commits once, the confirmation clears, and settings survive restart.
20. Repeat the Garden, Nursery, Story, movement, and Settings journeys with
    keyboard only, visible focus, reduced motion, minimum supported window size,
    Home, and native 3:2 compositions.
21. Restart only the disposable Anki process and re-verify the schema-25 SQLite
    reward authority, `starter_selection_complete`, nurtured plant, exact
    hundredth-Growth units, Stored Growth, checkpoint/Full Bloom metadata,
    streak, Garden Coin
    transactions, reward events, stable card lineages, achievement finalization,
    Garden Find outcomes/daily cap, per-tier environment guarantees, Today’s
    Cards projection, environment entitlements/locked and queued loadout/
    visibility, Growth Charge inventory, timed Fertilizer periods/queues,
    Booster card batches, collection,
    placements, stories, display preferences, pending sync receipt,
    completed-purchase replay history,
    and home visibility. Re-submit one completed purchase request and confirm
    its stored outcome returns without another debit or grant. Re-sync one
    already processed row and one late lower-ID row to verify restart
    idempotency.

Automated tests cover progression, migration, catalog readiness, UI contracts,
geometry, assets, packaging, and rollback. They do not replace this exact-package
isolated-Anki acceptance pass.
