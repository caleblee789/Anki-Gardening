# Anki Garden UI surface inventory

Status: current Release 2.1.0 capture contract v19. The exact ordered source is
`CAPTURE_FACE_GROUPS` in `ankigarden/capture_ui_faces.py`; the retained manifest
is the immutable record of the completed run:

`build/ui-face-captures/capture-sequence-20260823-000843/20260823-000847/manifest.json`

The contract contains 126 distinct functional/state faces captured once under
`QT_SCALE_FACTOR=1.0`. The manifest records 126/126 captures, primary display,
zero failures, and zero text-layout warnings. Its 17-page contact-sheet index
validates all 126 surfaces. Resize, breakpoint, 150%, and 200% screenshot
duplicates are excluded; those layouts remain automated geometry gates.

## Surface profiles

| Profile | Surface and entry point | Authoritative data | Primary behavior |
|---|---|---|---|
| First run | Home, Garden onboarding, starter Nursery and confirmation | Schema-21 onboarding, catalog, plants, slots, request revision | Choose starter, place, Nurture, resume, retry |
| Home | Deck Browser and Overview card | Shared preview snapshot, Garden metrics, scene and asset metadata | Open Garden, retry; no scene mutation |
| Garden | Dashboard, scene, popovers and landmarks | Plants, slots, active plant, Growth, effects, scene geometry | Select, Nurture, Move, Story, Progress, Collection, Nursery, Settings |
| Fertilizer | Application and replacement dialogs | Engine quote, target status, interval history, balance, replay record | Apply, extend, replace, keep current, retry |
| Progress | Growth, streak, Coins, Achievements and Collection | Canonical projections, reward ledger, catalog and ownership | Inspect, filter, target Charge, manage Collection |
| Collection | Item details and environment preview | Inventory, entitlements and one local loadout draft | Preview, apply atomically, cancel and restore |
| Nursery | Four commerce tabs | Engine catalogs, quotes, ownership, inventory, slots, manifest readiness | Purchase, use, unlock, plant, route to Collection |
| Growth Charge | Targeted Charge confirmation and result | Inventory, eligible target, quote/request/outcome, stage reward | Select Charge, use, retry, open Nursery |
| Settings | Display settings and diagnostics | Staged add-on config, Garden name, capabilities and telemetry | Save, cancel, restore, refresh/copy diagnostics |
| Reviewer | Nonmodal consolidated reward feedback | Committed reward/Find outcomes and presentation registries | Preserve review focus and acknowledge rendered events |

All mutations remain engine-authoritative, rollback-safe, and atomically saved.
Capture-only viewport, route, hover, focus, filter, and draft state must never be
persisted.

## Ordered capture groups

The group order below is the current manifest order. The manifest owns every
individual label, capture ID, renderer, realized size, fixture validation,
postcondition, and output path; duplicating all 126 records in prose would
create a second drift-prone authority.

| Order | Group | Faces | First label | Last label |
|---:|---|---:|---|---|
| 1 | First run | 6 | `starter-deck-browser-home` | `starter-action-above-footer` |
| 2 | Anki home | 2 | `deck-browser-home` | `overview-home` |
| 3 | Garden | 9 | `full-garden` | `plant-story` |
| 4 | Anki home — active after Nurture | 2 | `active-deck-browser-home-after-nurture` | `active-overview-home-after-nurture` |
| 5 | Garden Progress | 10 | `growth-zero` | `collection-species-overview` |
| 6 | Collection loadout details | 3 | `collection-loadout-detail` | `collection-preview-restored` |
| 7 | Nursery | 4 | `nursery-plants` | `nursery-weather-scenery` |
| 8 | Settings | 5 | `settings-home-preview-disabled` | `diagnostics-warning` |
| 9 | Release stress — Garden | 16 | `long-garden-name` | `fertilizer-replacement-confirmation` |
| 10 | Watering can — all six plots | 12 | `watering-can-garden-plot-1` | `watering-can-overview-plot-6` |
| 11 | Release stress — Progress | 7 | `collection-several-discovered` | `streak-achievement-earned-next` |
| 12 | Release stress — Nursery | 5 | `nursery-item-owned` | `missing-artwork-graphical-fallback` |
| 13 | Release stress — Settings and reviewer rewards | 7 | `settings-unsaved-changes` | `reviewer-find-stacked-sync` |
| 14 | Accessibility | 2 | `reduced-motion-enabled` | `keyboard-focus-state` |
| 15 | Resumable and resilient states | 8 | `starter-placement` | `collection-known-not-collected-overview` |
| 16 | Purchase confirmations and outcomes | 19 | `purchase-confirmation-species` | `collection-environment-mechanics` |
| 17 | Collection transactional states | 2 | `collection-loadout-persistence-error` | `collection-origin-plant-placement` |
| 18 | Growth Charge confirmation states | 7 | `growth-charge-use-ready` | `growth-charge-success-stage-reward` |

## Acceptance boundary

The current capture closes ordered macOS Qt automated completeness for this
source. It does not close native Windows/Linux behavior, true OS scaling or
mixed-DPI transitions, final-production restart/persistence, screen-reader,
human/device visual, or complete end-to-end acceptance.
