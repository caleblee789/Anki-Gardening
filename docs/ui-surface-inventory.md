# Anki Garden UI interface inventory

Status: current Release 2.1.0 capture contract v22. The exact ordered source is
`CAPTURE_FACE_GROUPS` in `ankigarden/capture_ui_faces.py`. Final immutable
manifest and contact-sheet paths are recorded in `ui/final-ui-audit-2.1.0.md`
only after a complete run passes independent validation.

The release contract contains 26 distinct interfaces, each captured once in a
stable representative state under `QT_SCALE_FACTOR=1.0`. The validator requires
26/26 ordered captures, zero failures and text-layout warnings, and four valid
contact-sheet pages. Raw manifest-owned PNGs remain the runtime geometry
authority; the sheets are review aids.

The former 126-state sequence remains source-owned as
`EXHAUSTIVE_CAPTURE_FACE_GROUPS` and is available through the explicit `full`
profile for targeted diagnosis. Alternate empty, loading, stale, error,
success, accessibility, resize, and stress states remain covered by automated
tests without repeating every state in the release sheet.

## Interface profiles

| Profile | Surface and entry point | Authoritative data | Primary behavior |
|---|---|---|---|
| First run | Garden onboarding, starter Nursery, and confirmation | Schema-21 onboarding, catalog, plants, slots, request revision | Choose starter, place, Nurture, resume, retry |
| Home | Deck Browser preview | Shared preview snapshot, scene and asset metadata | Open Garden, retry; no scene mutation |
| Garden | Dashboard, scene, plant card, Move, and Story | Plants, slots, active plant, Growth, effects, scene geometry | Select, Nurture, Move, Story, Progress, Collection, Nursery, Settings |
| Fertilizer | Application dialog | Engine quote, target status, interval history, balance, replay record | Apply or extend without duplicating purchase logic |
| Progress | Growth, streak, Coins, Achievements, and Collection | Canonical projections, reward ledger, catalog and ownership | Inspect progress and open Collection |
| Collection | Species overview and loadout details | Inventory, entitlements and one reversible loadout draft | Inspect, preview, apply atomically, cancel and restore |
| Nursery | Four commerce tabs plus a normal-flow receipt | Engine catalogs, quotes, ownership, inventory, slots, manifest readiness | Purchase, use, unlock, plant, route to Collection |
| Growth Charge | Targeted Charge confirmation | Inventory, eligible target, quote/request/outcome, stage reward | Select Charge, use, retry, open Nursery |
| Settings | Unsaved Display state and Diagnostics warning | Staged add-on config, Garden name, capabilities and telemetry | Save, discard, refresh/copy diagnostics |
| Reviewer | Consolidated nonmodal reward feedback | Committed reward outcomes and presentation registries | Preserve review focus and acknowledge rendered events |

All mutations remain engine-authoritative, rollback-safe, and atomically saved.
Capture-only viewport, route, hover, focus, filter, and draft state must never be
persisted.

## Ordered release groups

| Order | Group | Interfaces | First label | Last label |
|---:|---|---:|---|---|
| 1 | First run | 3 | `starter-garden-onboarding` | `starter-selection-confirmation` |
| 2 | Home and Garden | 6 | `full-garden` | `plant-story` |
| 3 | Progress | 5 | `growth-nonzero` | `progress-collection` |
| 4 | Collection and Nursery | 6 | `collection-species-overview` | `nursery-weather-scenery` |
| 5 | Settings and transactions | 6 | `settings-unsaved-changes` | `growth-charge-use-ready` |

The deterministic two-column renderer keeps whole groups where possible. These
five groups produce four pages: First run and Home/Garden share page 1; each
remaining group owns one page.

## Acceptance boundary

A complete v22 run closes only the ordered macOS Qt representative visual
inventory for its exact package. It does not replace the exhaustive automated
state matrix or close native Windows/Linux behavior, 125%/150% and true OS
scaling, mixed-DPI transitions, forced colors, screen-reader, broader keyboard,
human/device visual, or full end-to-end acceptance unless those gates are run
and recorded separately.
