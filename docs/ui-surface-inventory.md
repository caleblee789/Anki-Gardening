# Anki Garden UI interface inventory

Status: current Release 2.1.0 capture contract v25. The exact ordered source is
the Qt-free `SurfaceSpec` registry compiled into
`ankigarden/capture/capture-contract-v25.json`. Inspect it without mutation via
`python scripts/capture_sequence.py --list-surfaces` or explain one ID with
`--explain-surface ID`. Final immutable
manifest and contact-sheet paths are recorded in `ui/final-ui-audit-2.1.0.md`
only after a complete run passes independent validation.

The current v25 registry contains 17 representative and 33 full surfaces,
rendered as two and five sheets. Those values are generated observations, not
fixed acceptance constants. Redundant or behavioral-only IDs are permanently
retired, including the starter-confirmation ID and every watering-can capture.
Future counts are computed from active registry entries and their presentation
groups. Both profiles run under `QT_SCALE_FACTOR=1.0`. Null, blank, unpainted,
wrong-window, wrong-process, invalid-geometry/crop, open, cleanup, and checkpoint failures
reject a capture. Detailed semantic, copy, layout, scroll, and duplicate-view
findings are recorded as review advisories and never reject otherwise valid
pixels. Raw
manifest-owned PNGs remain the runtime geometry authority; the sheets are
review aids.

## Interface profiles

| Profile | Surface and entry point | Authoritative data | Primary behavior |
|---|---|---|---|
| First run | Garden onboarding, starter Nursery, and placement | Schema-22 onboarding, catalog, plants, slots, request revision | Choose starter, place, Nurture, resume, retry |
| Home | Deck Browser preview | Shared preview snapshot, scene and asset metadata | Open Garden, retry; no scene mutation |
| Garden | Dashboard, scene, plant card, Move, and Story | Plants, slots, active plant, Growth, effects, scene geometry | Select, Nurture, Move, Story, Progress, Collection, Nursery, Settings |
| Fertilizer | Application dialog | Engine quote, target status, interval history, balance, replay record | Apply or extend without duplicating purchase logic |
| Progress | Today’s Cards, Plant Growth, Anki streak, Garden Coins, Achievements, and Collection | Canonical projections, reward ledger, catalog and ownership | Open on Today’s Cards, inspect all six pages, and open Collection |
| Collection | Species overview and loadout details | Inventory, entitlements and one reversible loadout draft | Inspect, preview, apply atomically, cancel and restore |
| Nursery | Four commerce tabs plus a normal-flow receipt | Engine catalogs, quotes, ownership, inventory, slots, manifest readiness | Purchase, use, unlock, plant, route to Collection |
| Growth Charge | Targeted Charge confirmation | Inventory, eligible target, quote/request/outcome, stage reward | Select Charge, use, retry, open Nursery |
| Settings | Expanded Display state and Diagnostics warning | Staged add-on config, Garden name, capabilities and telemetry | Save, discard, refresh/copy diagnostics |
| Reviewer | Persistent content-driven HUD with integrated reward dock | Global Today’s Cards projection, committed plant/checkpoint state, active effects, stable reward bundles, and the local-session accumulator | Keep the shell mounted, update in place, collapse in one click, queue one major reveal at a time, and acknowledge stable event IDs without replay |
| Review exit | Focus-safe Session Summary over the normal Anki surface | Proven local session events, Today’s Cards start/end snapshots, exact Growth/Coins/Finds, milestones, discoveries, and frozen remaining effects | Inspect or dismiss the harvest report without blocking the underlying Anki page |

All mutations remain engine-authoritative, rollback-safe, and atomically saved.
Capture-only viewport, route, hover, focus, filter, and draft state must never be
persisted.

## Ordered profiles

Profile membership, groups, ordinals, and page counts are generated from the
registry. `--list-surfaces` is the human-readable inventory and
`--plan-only --profile PROFILE` is the single-session execution and checkpoint-domain view. Adding a surface
requires one registry row; removal retires its stable ID permanently; reordering
changes sheet presentation without invalidating that surface's PNG.

The full profile keeps one image per structurally distinct surface or
high-value interaction. Copy variants, transient loading states, transaction
error permutations, repeated plot positions, filtered views of the same
Collection window, locked variants of a captured Nursery tab, and alternate
host routes stay in focused parameterized tests instead of becoming duplicate
screenshots.

The representative profile includes the clean expanded Reviewer HUD, its
seven-event integrated reward-bundle state, and the Session Summary. The full
profile also includes the default Today’s Cards page in Garden Progress. The
Reviewer captures use a maximized window and prove content-driven shell bounds,
sticky-header/internal-scroll ownership, zero horizontal scroll, integrated
reward-dock containment, session-footer identity, and clearance above Anki’s
bottom controls.

## Acceptance boundary

A complete v25 `full` run closes the active ordered macOS Qt visual inventory
for its exact package and compiled contract. The representative run is
preflight evidence only. Neither tier closes native Windows/Linux behavior, 125%/150% and true OS
scaling, mixed-DPI transitions, forced colors, screen-reader, broader keyboard,
human/device visual, or full end-to-end acceptance unless those gates are run
and recorded separately.
