# End-to-end display assertions

Install the exact rebuilt `dist/anki_garden.ankiaddon` into a fresh, uniquely
named, disposable Anki 26.08 base/profile with sync disabled. Before any
interaction and again after restart, verify process identity, the unique
profile window, the disposable filesystem, and logged-out/sync-off state. Never
control the normal profile.

1. Launch cleanly with one **Tools → Anki Garden** action and no add-on warning.
2. Confirm Deck Browser and Overview show only the noninteractive scene,
   nurtured-plant Growth, Anki streak, Garden Coins, and **Open Garden**. Plant
   and Nursery clicks must do nothing there.
3. With fresh schema 14 state, choose **Open Garden** and confirm the Nursery
   opens automatically. It must offer every currently release-ready species as
   a free starter, show no hard-coded collection denominator, and leave the
   second unlocked direct-soil space empty after selection.
4. Before choosing a starter, answer a real card and verify study totals and the
   Anki streak advance while plant Growth stays at zero. Choose a starter and
   confirm the earlier answer is never backfilled.
5. In an established Garden, confirm the permanent strip contains only Plant
   Growth, Anki streak, and Garden Coins. **Progress** begins collapsed and
   reveals Today, Achievements, Collection, and recent Garden Coin activity.
6. Hover and keyboard-focus the Nursery building. Confirm restrained glow,
   **Open Nursery** tooltip, and click/Enter/Space activation. Confirm the
   target is disabled while moving a plant.
7. In Nursery, verify **Your plants** and **Available now** use data-driven
   counts. Bonsai, Rose, Sunflower, Lavender, Hydrangea, Peony, Foxglove,
   Japanese Maple, Wisteria, and Dahlia are stocked by the current complete V6
   lines, while seeded legacy-owned species remain visible and usable.
8. Buy, shelve, and replant a species; unlock spaces three through six; exercise
   insufficient balance, duplicate purchase, full garden, active-plant shelving,
   and failed-save paths. No rejected operation may spend Garden Coins or lose
   Growth, Story, or Fertilizer state.
9. Select plants at every scene edge and in intentional overlaps. Confirm one
   compact card, topmost-art hit testing, edge-safe placement, outside/Escape
   dismissal, and Nurture, Fertilize, Move, Story in a stable order.
10. Select **Move** and choose a highlighted direct-soil space by mouse and
    keyboard. Confirm empty moves and occupied swaps save immediately, locked
    spaces reject, Escape/Cancel exits before placement, save failure restores
    the previous arrangement, and the temporary **Undo** action restores the
    last successful move. There is no destination dropdown or Done button.
11. Open Fertilize and verify the three choice cards show exact Garden Coin
    cost, Growth-per-answer effect, and duration. Extend the same tier, reject
    then confirm replacement by a different tier, force expiry, and repurchase.
    Sync answers from before, during, and after each interval; confirm each uses
    the tier active at answer time and that the direct bonus disappears at the
    exclusive expiry without changing earned Growth.
12. Answer real Again and Good ratings. Each answer gives 10 base Growth only to
    the answer-time nurtured unfinished plant, plus the displayed streak and
    Fertilizer bonuses. Switch with **Nurture** and verify old Growth never moves.
13. Cross 25/50/75/100 stage-local milestones and one stage threshold. Confirm
    concise feedback, artwork transition, Garden Coin reason, and no disruptive
    modal. At Rare, confirm routing pauses until another unfinished plant is
    nurtured.
14. Exercise all due with due review, intraday learning/relearning, unseen new,
    active filtered, suspended, and buried cards. Confirm exact inclusion,
    exclusions, at-least-one-answer guard, one award, and no revocation.
15. Run same-day synced-answer catch-up and refresh twice. Sync a lower ID after
    a higher one and include prior-day and future/device-skew rows. Current-day
    supported rows apply exactly once; excluded rows create no Growth and are
    not consumed. Simulate review-log, scheduler-cutoff, and save failure, then
    retry and confirm no answer is lost or duplicated.
16. Open Plant Story and confirm the compact hero, inline rename, oldest-to-newest
    timeline, warm early-story state, **Up next**, keyboard flow, rename
    persistence, and local date formatting.
17. Open Settings and confirm the read-only Verdant Twilight card, real
    noninteractive live preview, Garden display and Motion sections, collapsed
    Fine tune controls, responsive stacking, and preserved Troubleshooting tab.
18. Stage settings and verify the preview updates immediately. Confirm Cancel
    restores persisted values, Restore defaults only stages values, Save settings
    commits once, the confirmation clears, and settings survive restart.
19. Repeat the Garden, Nursery, Story, movement, and Settings journeys with
    keyboard only, visible focus, reduced motion, minimum supported window size,
    4:3, 16:9, home, and wide compositions.
20. Restart only the disposable Anki process and re-verify schema 14,
    `starter_selection_complete`, nurtured plant, Growth, streak, Garden Coin
    processed-ID ledger, Fertilizer current/history intervals, collection,
    placements, stories, display preferences, and home visibility. Re-sync one
    already processed row and one late lower-ID row to verify restart
    idempotency.

Automated tests cover progression, migration, catalog readiness, UI contracts,
geometry, assets, packaging, and rollback. They do not replace this exact-package
isolated-Anki acceptance pass.
