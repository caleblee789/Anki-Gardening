# Anki Garden UI interface inventory

Status: current Release 2.2.0 capture contract v26, contract schema 2 and
scenario schema 3. The exact ordered source is the Qt-free `SurfaceSpec`
registry compiled into
`ankigarden/capture/capture-contract-v26.json`. Inspect it without mutation via
`python scripts/capture_sequence.py --list-surfaces` or explain one ID with
`--explain-surface ID`. The current immutable
[full manifest](../build/ui-face-captures/full/capture-sequence-20260831-155312/assembled/manifest.json)
and [five-page contact-sheet index](../build/ui-face-captures/full/contact-sheets/anki-garden-ui-contact-sheet-2.2.0-20260831-155312/contact-sheet-set.json)
are bound to the exact package and contract digest in the
[canonical UI audit](ui/final-ui-audit-2.2.0.md).

The current v26 registry contains 18 representative and 34 full surfaces,
rendered as two and five sheets. Those values are generated observations, not
fixed acceptance constants. Redundant or behavioral-only IDs are permanently
retired, including the starter-confirmation ID and every watering-can capture.
`nursery-weather-scenery` is retired; its ordinal-24 replacement is
`nursery-garden-decorations-scenery`.
Future counts are computed from active registry entries and their presentation
groups. Both profiles run under `QT_SCALE_FACTOR=1.0`. Null, blank, unpainted,
wrong-window, wrong-process, invalid-geometry/crop, open, cleanup, and
checkpoint failures reject a capture. Deprecated visible copy, DOM/root
overflow, progress fractions, asset mapping, Reviewer exclusion rectangles,
four-state scrolling, scenario identity, and per-step state contracts are also
hard gates. Narrow non-visible allowlists exist only for compatibility keys and
historical migration fixtures. Raw manifest-owned PNGs remain the runtime
geometry authority; the sheets are review aids.

## Interface profiles

| Profile | Surface and entry point | Authoritative data | Primary behavior |
|---|---|---|---|
| First run | Garden onboarding, starter Nursery, and placement | Schema-27 onboarding, catalog, plants, slots, request revision | Choose starter, place, Nurture, resume, retry |
| Home | Deck Browser preview | One renderer-neutral Home-card projection and shared preview snapshot | Render starter, empty, active, zero, partial, and complete states in one shell; Open Garden or retry without scene mutation |
| Garden | Dashboard, scene, plant card, Move, and Story | Plants, slots, active plant, Growth, effects, scene geometry | Select, Nurture, Move, Story, Progress, Collection, Nursery, Settings |
| Fertilizer | Application dialog | Engine quote, immutable source `plant_id`, target status, interval history, balance, and replay record | Keep one source through selection, quote, confirmation, and queued period; use Apply/Queue, Buy-and-apply/Buy-and-queue, and Extend only for the same-tier extension disposition |
| Progress | Today’s Cards, Plant Growth, Anki streak, Garden Coins, Achievements, and Collection | Canonical stage, `PlantIdentity`, Today’s Cards, reward, catalog, ownership, collection-count, and appearance projections | Open on Today’s Cards, inspect all six pages, and keep `10 of 10 species discovered` separate from `30 of 39 collection entries discovered` |
| Collection | Species overview and loadout details | Inventory, entitlements and one reversible loadout draft | Inspect, preview, apply atomically, cancel and restore |
| Nursery | Four commerce tabs plus a normal-flow receipt | Engine catalogs, quotes, ownership, inventory, slots, manifest readiness | Purchase, use, unlock, plant, route to Collection |
| Growth Charge | Targeted Charge confirmation | Inventory, eligible target, quote/request/outcome, stage reward | Select Charge, use, retry, open Nursery |
| Settings | Expanded Display state and Diagnostics warning | Staged add-on config, Garden name, sync-receipt presentation, capabilities and telemetry | Save, discard, refresh/copy diagnostics |
| Reviewer | Persistent content-driven HUD with integrated reward dock | Global Today’s Cards projection, committed plant/checkpoint state, active effects, stable reward bundles, and the local-session accumulator | Render the canonical `176 + 18 = 194` reconciliation, keep `Sprout · 2 of 6 stages`, and stay inside the 296/44/16 safe area with measured answer-control clearance and a 72 px fallback |
| Review exit | Focus-safe, nonmodal Session Summary over the normal Anki surface | Proven local session events, Today’s Cards start/end snapshots, exact Growth/Coins/Finds, milestones, discoveries, and frozen remaining effects | Keep session and daily scopes separate, including canonical `126 + 19 = 145`, while the shared summary coordinator owns mutual exclusion, focus restoration, and Escape |
| Sync completion | Upper-right, nonmodal Sync Rewards receipt over stable Anki Home | Presentation-ready committed rewards spanning every eligible imported answer since the desktop baseline, with exact Growth allocation, Finds, discoveries, progression, All Clear, and changed effects | Render canonical `420 + 80 + 20 = 520`, dock safely, and prioritize Full Bloom, stage change, the highest valid resulting-stage checkpoint, then ordinary Growth |

All mutations remain engine-authoritative, rollback-safe, and atomically saved.
Capture-only viewport, route, hover, focus, filter, and draft state must never be
persisted.

## Ordered profiles

Profile membership, groups, ordinals, and page counts are generated from the
registry. `--list-surfaces` is the human-readable inventory and
`--plan-only --profile PROFILE` is the single-session execution and
checkpoint-domain view. Adding a surface requires one registry row; removal
retires its stable ID permanently; reordering changes sheet presentation
without invalidating that surface's PNG.

Every spec, dependency digest, runtime record, manifest row, validator result,
contact-sheet index entry, and PNG metadata record carries `scenario_id`,
`fixture_id`, and a one-based `scenario_step`. Shared seeded lineages are
`first_run` for 01–04, `fertilizer_queue` for 09–10, and
`growth_charge_transition` for 33–34. Named single-surface scenarios are
`reviewer_hud_base` (27), `session_summary` (28), `sync_rewards` (29), and
`reviewer_hud_full_bloom` (30). Every other surface defaults to its stable ID,
fixture version `v1`, and step 1. Fixture identity denotes shared seeded
lineage; the exact state contract is still validated at every step. V25
evidence is categorically ineligible for v26 reuse.

The full profile keeps one image per structurally distinct surface or
high-value interaction. Copy variants, transient loading states, transaction
error permutations, repeated plot positions, filtered views of the same
Collection window, locked variants of a captured Nursery tab, and alternate
host routes stay in focused parameterized tests instead of becoming duplicate
screenshots.

The representative profile includes the clean expanded Reviewer HUD, its
seven-event integrated reward-bundle state, the Session Summary, and one rich
Sync Rewards receipt using `Rewards from 42 card answers on another device.`
The full profile also includes the default Today’s Cards page in Garden
Progress. The Reviewer captures use a maximized window and prove content-driven
shell bounds, sticky-header/internal-scroll ownership, zero horizontal scroll,
integrated reward-dock containment, session-footer identity, and clearance
above Anki’s bottom controls.

The art audit validates all 60 species-stage assets and all six bed positions.
Plant placement metadata serializes `visual_scale_correction`; both scene art
and thumbnails consume the calibrated scale rather than applying
screenshot-specific sizing.

## Acceptance boundary

A complete v26 `full` run closes the active ordered macOS Qt visual inventory
for its exact package and compiled contract. The representative run is
preflight evidence only. The current independent validator found 34 valid
surfaces across five pages with no advisories and the automated gate passed;
34/34 raw PNGs and 5/5 sheets were also visually reviewed. Those results do
not close manual macOS interaction, native Windows/Linux behavior, 125%/150%
and true OS scaling, mixed-DPI transitions, forced colors, screen-reader,
broader keyboard, human/device visual, or full end-to-end acceptance. The
add-on remains `quality_status: review-required`, `release_ready: false`, and
unpublished until the separate gates are run and human release approval is
recorded.
