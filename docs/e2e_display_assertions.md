# End-to-end display assertions

Install the exact rebuilt `dist/anki_garden.ankiaddon` into a fresh, uniquely
named, disposable Anki 26.08 base/profile with sync disabled. Before any
interaction and again after restart, verify process identity, the unique
profile window, the disposable filesystem, and logged-out/sync-off state. Never
control the normal profile.

1. Launch cleanly with one **Caleb M. Add-ons Settings → Anki Garden settings** action, no direct **Tools → Anki Garden** action, and no add-on warning.
2. Confirm Deck Browser and Overview show only the noninteractive scene,
   nurtured-plant Growth, Anki streak, Garden Coins, and **Open Garden**. Plant
   and Nursery clicks must do nothing there.
3. With fresh schema 18 state, choose **Open Garden**, verify the introduction,
   and proceed to the Starter Nursery. It must offer every release-ready species
   as a free starter and show no hard-coded collection denominator. Complete
   confirmation, placement, nurture, and completion; the other unlocked
   direct-soil space remains empty.
4. Before choosing a starter, answer a real card and verify study totals and the
   Anki streak advance while plant Growth stays at zero. Choose a starter and
   confirm the earlier answer is never backfilled.
5. Confirm the Garden name is centered inside the themed frame. Activate Plant
   Growth, Anki streak, and Garden Coins by mouse and keyboard; verify each
   focused detail and its relative bar/rules. Header **Progress** must open
   Today, Achievements, Collection, Weather & Scenery, and How it grows in a
   separate window.
6. Hover and keyboard-focus Nursery and cottage. Confirm silhouette-following
   outlines, anchored labels, click/Enter/Space activation, and no empty-air
   rectangle. Confirm both targets are disabled while moving a plant.
7. In Nursery, verify **Plants**, **Supplements & Boosters**, **Permanent
   Upgrades**, and **Weather & Scenery** tabs. Plant counts are data-driven;
   stage artwork is clear; Bonsai, Rose, Sunflower, Lavender, Hydrangea, Peony, Foxglove,
   Japanese Maple, Wisteria, and Dahlia are stocked by the current complete V6
   lines, while seeded legacy-owned species remain visible and usable.
8. Purchase, move to Collection, and plant in garden a species; unlock spaces
   three through six sequentially; purchase Small/Standard Growth Charges and
   use all three tiers; purchase a Weather and Scenery and confirm neither
   auto-equips. For every Coin purchase, inspect artwork, item/category/quantity,
   exact mechanics, target where applicable, price, current/resulting balance,
   Cancel focus, disabled submission, and receipt. Exercise insufficient
   balance, persistence failure/retry, unavailable, already-owned, invalid
   target, stale price/balance, duplicate request, full garden, active-plant
   storage, and failed-save paths. No rejected operation may spend Garden Coins
   or lose Growth, Story, Fertilizer, Booster, inventory, or bed state.
9. Select plants at every scene edge and in intentional overlaps. Confirm one
   compact card, topmost-art hit testing, edge-safe placement, outside/Escape
   dismissal, and Nurture, Fertilize, Move, Story in a stable order.
10. Select **Move** and choose a highlighted direct-soil space by mouse and
    keyboard. Confirm empty moves and occupied swaps save immediately, locked
    spaces reject, Escape/Cancel exits before placement, save failure restores
    the previous arrangement, and the temporary **Undo** action restores the
    last successful move. There is no destination dropdown or Done button.
11. Open Fertilize and verify Basic, Quality, and Magical cards show exact
    Garden Coin cost, Growth-per-answer effect, duration, and labeled item art. Extend the same tier, reject
    then confirm replacement by a different tier. The comparison must show both
    exact effects/durations and the precise active time discarded, stacking at
    narrow widths and balancing side by side when measured space fits. Force
    expiry and repurchase.
    Sync answers from before, during, and after each interval; confirm each uses
    the tier active at answer time and that the direct bonus disappears at the
    exclusive expiry without changing earned Growth. Seed a Booster Potion,
   use and extend it, and verify +5 stacks with Fertilizer for exactly two hours.
   Equip Snow Flurry plus Full Moon and verify newly used Potions last 35%
   longer.
12. Answer real Again and Good ratings. Each answer gives 10 base Growth only to
    the answer-time nurtured unfinished plant, plus the displayed streak and
    Fertilizer, Booster, Weather, and Scenery bonuses. Switch with **Nurture**
    and verify old Growth never moves. Confirm Growth details separate Weather,
    Scenery, and Charge totals.
13. Cross 25/50/75/100 stage-local milestones and one stage threshold. Confirm
    concise image-led feedback, artwork transition, Garden Coin reason, and no disruptive
    modal. Seed every deterministic reward band in priority order, tier-complete
    Charge fallbacks, Ultra pity boundaries/reset, and all three scenery daily
    gifts; verify one reward slot per answer and no replay. At Rare, confirm
    routing pauses until another unfinished plant is
    nurtured.
14. Exercise all due with due review, intraday learning/relearning, unseen new,
    active filtered, suspended, and buried cards. Confirm exact inclusion,
    exclusions, at-least-one-answer guard, one award, and no revocation.
15. Run same-day synced-answer catch-up and refresh twice. Sync a lower ID after
    a higher one and include prior-day and future/device-skew rows. Current-day
    supported rows apply exactly once; excluded rows create no Growth and are
    not consumed. Simulate review-log, scheduler-cutoff, and save failure, then
    retry and confirm no answer is lost or duplicated.
16. In the cottage's **Weather & Scenery** tab, inspect every shared exact
    mechanic, textual Equipped state, how-to-earn entry, locked silhouette,
    ordered odds, and current Ultra pity. Confirm Collection is read-only and
    routes to Customize; equip every Weather and Scenery and toggle each visual
    layer there, then confirm its passive still applies. Inspect all 4:3, 16:9, and home reskins:
    plants, path, Nursery, cottage, occlusion, and hotspots must not move.
17. Open Plant Story and confirm enlarged actual-stage art, distinct editable
    name/species/stage labels, relative Growth bar, inline rename, oldest-to-newest
    timeline, warm early-story state, **Up next**, keyboard flow, rename
    persistence, and local date formatting.
18. Open Settings and confirm the read-only Verdant Twilight card, real
    noninteractive live preview, and applicable Garden display/notification
    controls. Confirm Weather/Scenery, art quality/detail/performance, animation,
    and Fine tune controls are absent; reduced motion remains automatic.
19. Stage settings and verify the preview updates immediately. Confirm Cancel
    restores persisted values, Restore defaults only stages values, Save settings
    commits once, the confirmation clears, and settings survive restart.
20. Repeat the Garden, Nursery, Story, movement, and Settings journeys with
    keyboard only, visible focus, reduced motion, minimum supported window size,
    4:3, 16:9, home, and wide compositions.
21. Restart only the disposable Anki process and re-verify schema 18,
    `starter_selection_complete`, nurtured plant, Growth, streak, Garden Coin
    processed-ID ledger, reward history, Ultra pity, daily claims, environment
    entitlements/loadout/visibility, Growth Charge and Booster inventory/current/history,
    Fertilizer current/history intervals, collection,
    placements, stories, display preferences, completed-purchase replay history,
    and home visibility. Re-submit one completed purchase request and confirm
    its stored outcome returns without another debit or grant. Re-sync one
    already processed row and one late lower-ID row to verify restart
    idempotency.

Automated tests cover progression, migration, catalog readiness, UI contracts,
geometry, assets, packaging, and rollback. They do not replace this exact-package
isolated-Anki acceptance pass.
