# Comprehensive QA and remediation report

- Date: 2026-08-10
- Branch: `codex/clean-and-publish-garden`
- Anki runtime target: 26.08
- Package line: `2.1.0`, state schema 14, scene geometry 6

## Current release status

Verdant Twilight V6 and the schema 14 garden-first interface supersede the
earlier placement candidate. Do not reuse old package hashes, hard-coded test or
asset counts, screenshots, or runtime acceptance claims. Release acceptance is
earned only after rebuilding the final source, passing every gate below, and
testing that exact archive in an identity-verified disposable Anki profile.

## Current remediation contract

| Area | Required result |
|---|---|
| State | Schema 14 keeps transactional fresh-starter selection, a bounded current-scheduler-day processed-ID ledger, a compatibility-only scalar cursor, answer-time Nurture periods, and bounded per-plant Fertilizer activation history. Schemas 10–13 migrate without reviving removed progression systems or losing entitlement-only species. |
| Scene | Verdant Twilight V6 provides six direct-soil spaces, responsive composition, depth/occlusion metadata, and the manifest-backed Nursery landmark. |
| Home | Deck Browser and Overview show only noninteractive art, nurtured-plant Growth, Anki streak, Garden Coins, and Open Garden. |
| Garden | A compact three-metric strip remains above the scene; Today, Achievements, Collection, detailed Growth, and Coin activity live in collapsed Progress. |
| Nursery | First Open Garden auto-opens one free starter. Later access is through the full-Garden landmark only. Stock is derived from complete release-preferred V6 stage lines; current ready species are Bonsai, Rose, Sunflower, Lavender, Hydrangea, Peony, Foxglove, Japanese Maple, Wisteria, and Dahlia. |
| Plant actions | The compact card uses Nurture, Fertilize, Move, and Story. Move selects scene destinations directly, saves immediately, and offers Undo without a dropdown or Done button. |
| Fertilizer | Cards disclose exact Coin cost, direct Growth effect, and duration before purchase. Bonus eligibility is `started_at <= answer_time < expires_at`; same-tier extension remains one interval, replacement truncates and archives the old tier, expired repurchase retains the prior interval, and save/cap failure spends nothing. |
| Story | Timeline is oldest to newest with compact hero, inline rename, early-story state, and Up next. |
| Settings | Read-only Verdant Twilight card, real live preview, Garden display, Motion, collapsed Fine tune, explicit Save/Cancel, staged defaults, and preserved Troubleshooting. |
| Language | Learner-facing surfaces use Nurture and Garden Coins. Internal compatibility fields such as `active_plant_id` and `currency_balance` remain unchanged. |

## Required automated and package gates

- Complete pytest suite with no failures.
- Python compilation with an isolated cache location.
- Asset audit, V6 release-readiness checks, and all-stage/all-space geometry and
  responsive-render validation.
- Deterministic package build, ZIP integrity, package-content checks, and
  byte-for-byte source/archive parity for shipped files.
- `git diff --check` and a stale-copy audit covering schema version, learner
  terminology, home metrics, Nursery access, movement controls, Story ordering,
  Settings behavior, scheduler-day ledger boundaries, and Fertilizer interval
  history.
- Record the final commands, results, artifact file count, and SHA-256 only after
  the source is frozen; never carry forward historical counts.

## August 10 V6 plant-library revision evidence

The ten-line Verdant Twilight library now uses one standardized progression:
Seed, Sprout, Young, Mature, Flowering, and Rare. All 60 canonical plant sprites
have exact source-master/hash metadata, normalized transparent canvases, and
bottom-center direct-soil placement. Rare stages use a related but structurally
different silhouette plus species-specific color/material and restrained magical
effects; Flowering remains the natural botanical peak.

- Strict review builder: 10/10 complete lines and three current review sheets in
  `build/twilight-full-library-review/`.
- Source audit: 60 exact-key `#FF00FF` masters verified; no missing or
  unmanifested V6 runtime sprites.
- Responsive placement: 210 plant assets across 20,160 scenarios, with 0
  failures and 0 warnings.
- Automated regression: 1,310 tests passed; isolated-cache compilation,
  package checks, ZIP integrity, and `git diff --check` passed.
- Final archive: 480 files, 201,812,727 bytes, SHA-256
  `34110916fa719c3442326608772c5581a7c7cb30faa21f78f963667f27241b7c`.
- Cleanup: 190 MiB of rejected candidates, duplicate Rose aliases, obsolete V4
  evidence, stale/mislabelled live-QA output, caches, and reproducible superseded
  review folders were moved to the recoverable macOS Trash bundle
  `Anki-Garden-cleanup-20260810-v6-library`. Accepted masters, compatibility
  inputs, the current full-library sheets, and final provenance were retained.

Exact-package isolated-Anki checks have verified the unique process, window,
filesystem, and sync-disabled profile gates, the ten-species Nursery, the Home
Widget, and the live Rose Seed scene. The remaining live Flowering/Rare A/B
capture was interrupted when the Mac locked; until that capture is completed,
the strict responsive sheets are the final visual evidence and live acceptance
is intentionally partial.

## Required exact-package isolated-Anki acceptance

Use a fresh, uniquely named disposable base/profile with sync disabled. Before
interacting—and again after restarting only the disposable process—verify:

1. Process identity: no command was forwarded to an existing normal Anki
   process.
2. Window identity: the visible window belongs to the unique disposable
   profile.
3. Filesystem identity: loaded add-on and collection paths are inside the
   disposable base.
4. Sync identity: the disposable profile is logged out or otherwise provably
   sync-disabled.

Then complete every journey in `e2e_display_assertions.md`, including fresh
starter choice, preselection review behavior, both home surfaces, Nursery
mouse/keyboard access, dynamic stock, collection transactions, direct Move and
Undo, Fertilizer cards, real reviews and catch-up, Story, Settings,
accessibility, reduced motion, responsive layouts, and restart persistence.

The catch-up journey must include an out-of-order lower ID after a higher ID,
prior-day and future/device-skew rows, database/cutoff/save failure followed by
retry, and a restart. Only supported rows in `[scheduler-day start, cutoff)` may
be marked processed; every eligible row must apply exactly once. The Fertilizer
journey must sync answers before, during, and after activation, then repeat after
same-tier extension, tier replacement, expired repurchase, and restart.

Record the accepted archive hash and identity evidence here only after all four
gates and every required journey pass. Until then, the current candidate is not
release-accepted.
