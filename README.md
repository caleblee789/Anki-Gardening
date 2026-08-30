# Anki Garden 🌿

Anki Garden is a calm, local-first Anki add-on that turns completed cards into a growing hand-painted garden.

> Cards complete → Growth → plant stages
>
> Today’s Cards, streak rewards, achievements, plant stages, and Garden Finds → rewards → plants, earned beds, supplements, Decorations, Scenery, Landmarks, and Mastery

For exact current Growth, reward, consumable, Garden Decoration, Scenery, Garden Find,
achievement, and economy rules, see the
[progression, rewards, and effects reference](docs/progression-rewards-effects-reference.md).

## Current release highlights

- The 2.2.0 economy keeps rating-neutral 10-Growth answers, replaces
  speed-dependent Fertilizer with card-counted value, lowers Full Bloom to
  35,000 Growth, limits six-bed output to 150%, and uses completion-based
  Garden Rhythm instead of streak Growth.
- Every starter appearance is economically equal, every later species costs
  250 Coins, Beds 3–6 are earned from plant progression, and optional cosmetic,
  Garden Landmark, and Cultivation Mastery sinks keep Stored Growth useful
  after the base collection is complete.
- A clearer first-run path explains that plant Growth and repeatable rewards begin
  after the learner chooses and nurtures a starter and are not backfilled;
  reliably reconstructable one-time achievements are handled separately from
  authoritative review history.
- Home, Garden, Nursery, Garden Progress, Settings, plant cards, and reviewer notices now share consistent learner-facing copy, accessible focus states, control sizing, and reduced-motion behavior.
- Native controls now share one semantic theme, DPR-aware icon cache, and visible
  switch-state treatment, keeping interaction geometry and state feedback
  consistent across Settings, Garden Progress, Collection, Nursery, and
  transaction dialogs.
- The fixed-height Home preview keeps the garden name, nurtured plant, Growth, and **Open Garden** visible without duplicating Today’s Cards, Anki streak, or Garden Coins; the full Garden provides the richer progression and interaction detail.
- Native dialogs now fit their visible state, use one deliberate overflow owner, normal-flow feedback and footers, text-fit button sizes, and compact left-accent status banners. Every add-on window now uses a native parented dialog, and visibility-sensitive controls receive parents before they can be shown; an opt-in audit can report unexpected parentless windows without creating native handles.
- The full Garden uses one centered 1260 × 840 (3:2) release canvas. Existing 4:3 scenery art covers that canvas at 50% 48%, preserving horizontal composition and cropping vertically without stretching.
- Reviewer progression stays inside one compact, content-driven HUD. Routine answers update the plant and session totals in place; meaningful committed rewards use one integrated reveal and one correlation-bound bundle rather than detached toast cards.
- Steady-state review maintenance reuses only an unchanged scheduler-day, review-history, and ledger signature. Proven local card completions use a narrow bounded lookup when safe, while sync, undo, collection reload, or ambiguity invalidates that proof and restores the complete fail-closed reconciliation path.
- Hidden progress pages render lazily, wall-time refresh timers run only while visible timed status exists, static scene animation timers stop, and bounded per-widget caches reuse scene layout and raster work without changing learner state.
- Runtime artwork now uses manifest-owned, pixel-lossless WebP files while preserving the approved V6 geometry, masks, transparent edges, and code-native missing-art fallbacks.
- Runtime asset checks use bounded container reads and a path/size/mtime cache, avoiding repeated multi-megabyte reads and ordinary metadata writes without changing selection or fallback behavior.
- Capture contract v26 uses contract schema 2 and scenario schema 3 to compile one Qt-free surface registry into an immutable manifest. The representative/full profiles contain 18/34 structurally distinct surfaces and two/five generated sheets. Every v26 surface records `scenario_id`, `fixture_id`, and one-based `scenario_step`; the shared lineages are `first_run` 01–04, `fertilizer_queue` 09–10, and `growth_charge_transition` 33–34, while 27–30 use named single-surface scenarios and all other surfaces default to their stable ID, fixture `v1`, and step 1. V25 evidence is frozen but rejected for v26 reuse. Native dialogs use fail-closed `QWidget.grab()` acquisition; Home and Reviewer prefer a verified app-owned Qt/WebView image and permit a compositor fallback only after exact process, window, geometry, DPR, semantic identity, overlay, and crop checks. Deprecated visible copy, DOM/root overflow, progress fractions, asset mapping, Reviewer exclusion rectangles, four-state scrolling, acquisition, lifecycle, and lineage are hard gates. A normal profile opens one disposable Anki process, captures every selected surface with checkpoint restoration between surfaces, and records clean shutdown from that same process. Memory-leak probing is not part of capture.

## Gameplay terms

| Term | What it means | Gameplay effect |
|---|---|---|
| **Completed card** | Finishing a card or learning step that Anki Garden can count. | Gives the unfinished plant you nurture **10 base Growth**. Again, Hard, Good, and Easy give equal ordinary Growth. |
| **Nurture** | Choose which unfinished plant receives future Growth. | Switching plants never moves Growth already earned. |
| **Growth** | A plant's progress toward its next visual stage. | Unlocks Seed, Sprout, Young, Mature, Flowering, and Full Bloom stages. |
| **Answer Growth** | Growth calculated when a card is completed. | Combines 10 base Growth with Garden Rhythm, Fertilizer, Potion, the snapshotted Garden Bonus, and Scenery Effect. Each other planted bed creates a separate 10% Shared Growth lane. |
| **Instant Growth** | A fixed Growth reward from Finds, Growth Charges, or completion effects. | Uses no card modifiers and is not shared, but overflow is redirected or stored instead of lost. |
| **Garden Rhythm** | Verified Today’s Cards completions among the prior seven eligible study days. | Adds 0–10% to the 10 base Growth without a missed-day reset cliff. Anki streak remains separate for streak Coins and achievements. |
| **Today’s Cards** | The live collection-wide cards and learning steps that must be finished before Anki's cutoff. | Completing them grants 10 Garden Coins and the locked Scenery completion gift. |
| **Garden Coins** | A separate spendable reward recorded in the reward and transaction ledgers. | Earned from daily study, streak rewards, achievements, Today’s Cards, plant milestones, environment effects, and Garden Finds; spent in the Nursery. |
| **Garden Find** | A deterministic chance after an eligible, newly processed card, with protection from long gaps and a daily limit. | Can grant Garden Coins, Instant Growth, a consumable, or an unowned Garden Decoration or Scenery item. |
| **Fertilizer** | A card-counted bonus to Answer Growth. | Adds `+1` for 100, `+2` for 200, or `+3` for 400 eligible cards. Review speed and time outside Anki do not change its value. |
| **Booster Potion** | A rare, non-purchasable study gift kept in your collection. | Adds `+5` Growth for the next 100 applicable cards and stacks with Fertilizer. |
| **Growth Charge** | A stored one-use supplement applied to any owned, planted, unfinished plant. | Adds `+100`, `+500`, or `+2,000` Instant Growth. Any excess is redirected or stored. |
| **Garden Decoration** | One displayed prop chosen independently from one active Garden Bonus. | Appearance can change without changing the day’s snapshotted mechanics. |
| **Scenery** | One displayed garden setting chosen independently from one active Scenery Effect. | Appearance and mechanics may come from different owned Scenery entries. |
| **Stored Growth** | Exact Growth that no unfinished planted target could accept. | Funds cosmetic Garden Landmark projects and per-species Cultivation Mastery; it never decays. |

## Progression details

- Every eligible completed card calculates the nurtured plant’s base Growth and all active modifiers exactly once. The nurtured plant receives the full result.
- Every other planted plant creates an exact 10% Shared Growth lane. A plant
  still growing receives its own share. A Full Bloom plant’s share is divided
  exactly among the planted plants still growing, including the nurtured plant.
  Fractions are preserved.
- Six planted beds therefore retain 150% total garden output while at least one
  plant remains unfinished.
- Garden Rhythm adds `0%`, `2%`, `4%`, `6%`, `8%`, or `10%` to base
  Growth for `0–1`, `2`, `3`, `4`, `5`, or `6–7` verified completions among
  the prior seven eligible study days. The first answer snapshots the tier.
- Plants use Seed, Sprout, Young, Mature, Flowering, and player-facing **Full Bloom** stages at `0`, `400`, `2,000`, `6,000`, `15,000`, and `35,000` Growth.
- Shared progression projections preserve internal `rare` state while displaying **Full Bloom**. Compact status identifies both stage and position, for example `Sprout · 2 of 6 stages`.
- Each stage pool pays at 25%, 50%, 75%, and completion. Full Bloom also grants one Small Growth Charge, a permanent collection record, and automatic continuation to the next planted unfinished plant.
- Growth never disappears at a plant cap or when no plant is selected. It continues to another eligible plant or enters Stored Growth until the learner chooses a plant.
- After activation, each eligible newly processed card independently checks the Standard and unowned-environment Garden Find pools. The Standard cap is three below 200 cards, four at 200–399, and five at 400 or more. A Standard Find and an environment discovery may stack with other rewards from the same card.
- Standard Find Growth is Instant Growth. It receives no streak or card modifier and is not shared. If no plant can receive it, the complete value enters Stored Growth.

## Anki-day reward rules

An Anki day follows Anki's configured next-day cutoff. The first eligible completed card starts or continues the streak and grants 2 Garden Coins.

Every seventh active-streak day grants 10 Garden Coins. One-time achievements
may stack with recurring rewards. Completing **Today’s Cards** grants 10 Garden
Coins plus the locked Scenery completion gift. The first valid completion also
grants a 5-Coin first-completion bonus. A single learner-facing result groups
every reward produced by the same completed card.

Today’s Cards uses a live collection-wide check at the moment of completion. It includes:

- new and review cards exposed by Anki’s active deck limits, including active filtered decks;
- learning and relearning steps due before Anki's next-day cutoff;
- cards restored from suspended or buried state before the award, if they are then due.

Scheduler-available new cards count from the start; moving one into Learning does not mark it complete. Cards remain excluded while suspended or buried. At least one eligible card must be completed, the reward can be earned once per Anki day, and it is never revoked after being granted.

The compact HUD keeps Today's Cards globally scoped. In progress it emphasizes
the number of **cards left** alongside completed/starting progress. Completion
becomes **Today’s Cards Complete**, the exact Coin reward, and the committed
cards-complete total. Find caps,
pity state, `Daily limit reached`, and an `ALL DECKS` control are never persistent
Reviewer copy.

The canonical reconciled displays keep their scopes explicit: the HUD renders
`176 + 18 = 194` cards due at the start, Session Summary renders
`126 + 19 = 145` cards complete, and Sync Rewards renders
`420 + 80 + 20 = 520` Growth. Session totals never replace daily totals.

Before a normal sync, Garden reconciles review history already present on the
desktop to establish a clean boundary. After sync, every previously unseen,
supported post-activation answer introduced beyond that boundary is processed
exactly once across its original Anki days, including delayed or out-of-order
rows whose IDs are lower than the desktop's latest answer. Past-day answers
receive their normal per-answer rewards; Today's Cards completion is evaluated
only for the current Anki day, where the live due state can still be verified.

Rewards and the pending nonmodal sync receipt are committed together before the
receipt can appear. Initial setup and one-way collection replacement establish a
non-awarding baseline instead of replaying history. Disabling **Show rewards
after syncing** suppresses only the receipt, not reward processing.

## Garden interaction

- Hover gives visible artwork a restrained highlight and pointer cursor without opening details or moving the art.
- Click selects one plant and opens a compact native card near it with stage-local Growth, today’s allocation, Fertilizer and Booster Potion status, and stable actions including Nurture, Fertilize, Growth Charge, Move, and Story.
- Click outside or press Escape to dismiss. The card repositions at scene edges and is replaced immediately when another plant is selected.
- Move highlights valid garden spaces. Click or keyboard-select one to save immediately, then use the inline Undo action if needed; Escape cancels before placement.
- Overlap hit testing follows depth order, and geometry-v2 `interaction_bounds` keep transparent artwork margins from stealing clicks.

The named Garden header, metric strip, and scene share one themed frame. Plant Growth, Anki streak, and Garden Coins are real buttons that open focused explanations with relative progress. **Garden Progress** reopens the last valid session page and defaults to **Today’s Cards**; the cottage always opens **Collection**. Navigation is Today’s Cards, Plant Growth, Anki Streak, Garden Coins, Achievements, and Collection. Plant-specific information lives in the clicked-plant card, Plant Growth, or Plant Story.

Verdant Twilight V6 uses six direct-soil beds across three staggered perspective
bands. The nursery entrance is a keyboard-accessible landmark that opens the
Nursery from the full Garden, is disabled while moving a plant, and is not exposed
in the home preview. A fresh garden presents starter setup in the Garden and
opens the Nursery when the learner chooses that action. Any one release-ready
species may be chosen free; every appearance grows at the same rate. The fresh
Garden begins with a second empty unlocked bed.
Garden naming is optional personalization in Settings; unnamed Gardens display
**My Garden**. New plants begin with an unambiguous generated name such as
**Bonsai Plant**. The Nursery is a warm catalog with **Plants**, **Fertilizers and
boosts**, **Garden beds**, and **Garden Decorations and Scenery** tabs, stage artwork
previews, and item art.

## Fertilizer and collection

- Basic Fertilizer: 30 Garden Coins, `+1` Growth for 100 eligible cards.
- Quality Fertilizer: 100 Garden Coins, `+2` Growth for 200 eligible cards.
- Magical Fertilizer: 300 Garden Coins, `+3` Growth for 400 eligible cards.

Fertilizer never expires with wall-clock time. Only an eligible committed
answer that receives the effect consumes one card. Same-tier doses add card
counts; different tiers remain in FIFO activation order. Up to five doses may
be active or queued; a rejected dose remains in inventory. At Full Bloom,
remaining card-counted value transfers to the automatically selected plant or
waits for the next Nurture choice when no recipient exists.

Booster Potions are not sold. Garden rewards can add them to the collection;
using one grants `+5` Growth for the next 100 eligible cards. Herbalist’s
Hourglass snapshots 125 cards instead. Full Moon Garden awards a Potion every
six active completion days but does not extend it. Potions stack with
Fertilizer.
Using another Potion extends the remaining card count.

Small and Standard Growth Charges can be bought repeatedly for 30 and 125
Garden Coins. They add 100 and 500 Instant Growth. The 2,000-Growth Grand
Charge is earned from Botanical Collection, Old Growth, and qualifying future
major rewards. A Charge can target any owned, planted,
unfinished plant from its selected-plant panel or Plant Growth card.
Confirmation revalidates the target, inventory, Growth, reward terms, and
request identity; it receives no card modifiers and is not shared. Overflow is
redirected or stored. Normal milestone and Coin rewards still apply. A failed save restores Growth,
inventory, rewards, feedback, and the replay ledger.

## Garden Decorations, Scenery, and Garden Finds

Exactly one owned Garden Decoration may be displayed, and one owned decoration
supplies the Garden Bonus. Those choices may differ. Displayed Scenery and the
active Scenery Effect are also independent. One effect stacks with the single
Garden Bonus.
The Nursery sells one-time Common and Uncommon choices but never auto-activates a
purchase. The Garden Progress cottage's **Garden Decorations and Scenery** collection tab shows the active
loadout, every effect, how each item is earned, exact drop odds, and finite
progress to each environment guarantee.
Find-only art remains a silhouette until unlocked while its rules stay visible.
The first eligible answer snapshots Garden Rhythm, the Garden Bonus, and the
Scenery Effect for that Anki day. Later mechanical changes queue for the next
Anki day and cannot stack. Displayed Decoration and Scenery may change at any
time. Separate
visibility switches hide either visual layer without disabling its effect.

The [illustrated 2.1.0 Garden Decorations reference](docs/references/garden-decorations-reference.docx)
is retained for visual provenance; the linked progression reference above is
the current 2.2.0 mechanic authority.

Garden Decorations and Scenery stay within a bounded daily power budget. Completion gifts
trigger only when Today’s Cards is complete, not from opening the reviewer or
completing a single card. Each gift has its own durable reward identity and does
not suppress either Garden Find pool.

| Garden Decoration | Acquisition | Garden Bonus |
|---|---|---|
| Seedling Sign | Included | None |
| Wind Chime | Nursery: 100 Coins | +1 Growth every 10 eligible cards |
| Harvest Bell | Nursery: 175 Coins | +5 Coins when Today’s Cards is complete |
| Watering Station | Nursery: 250 Coins | +1 Growth every 5 eligible cards among the first 100 daily |
| Herbalist’s Hourglass | Nursery: 350 Coins | Booster every 30 active completions; activated Potions receive 25 extra cards |
| Firefly Lantern | Rare environment discovery | +3 Instant Growth every 5 eligible cards to the closest checkpoint |
| Prism Trellis | Very Rare environment discovery | Banks 1 Growth on the first 100 daily cards, up to 300, and releases it on completion while active |

The Standard Find pool contains Garden Coin awards, 40/60/100 Instant Growth,
Small and Standard Growth Charges, Basic Fertilizer (shown as **Rich Compost**),
a Booster Potion, and the exceptional 40-Coin Garden Treasury. The full Garden
may explain the cap, protection, and guarantee; the persistent Reviewer HUD
shows a Find only when it is earned and never exposes those counters. The
independent environment
tiers use base chances of `1 in 2,500`, `1 in 10,000`, and `1 in 25,000`.
Rare, Very Rare, and each Ultra Rare item are guaranteed within
`10,000`/`40,000`/`50,000` eligible cards or `60`/`180`/`365` verified
Today’s Cards completions, whichever arrives first.

The configured roster contains ten direct-soil species—Bonsai, Rose, Sunflower,
Lavender, Hydrangea, Peony, Foxglove, Japanese Maple, Wisteria, and Dahlia—and
up to six garden beds. All ten species have identical mechanics: one chosen
starter is free and every other species costs 250 Garden Coins. Moving a plant
to Collection preserves its Growth and story. Beds 1–2 are included; Beds 3–6
are earned at first Mature, first unique Full Bloom, three unique Full Blooms,
and six unique Full Blooms.

Collection reports species and catalog coverage separately: the canonical
fixture shows `10 of 10 species discovered` and
`30 of 93 collection entries discovered`. The latter is never labeled as a
plant count.

| Species | Garden Coins |
|---|---:|
| Bonsai | 250 |
| Rose | 250 |
| Sunflower | 250 |
| Lavender | 250 |
| Hydrangea | 250 |
| Peony | 250 |
| Foxglove | 250 |
| Japanese Maple | 250 |
| Wisteria | 250 |
| Dahlia | 250 |

Five optional cosmetic Display Decorations cost 150–400 Coins. After the
first Full Bloom, Stored Growth and Coins may fund six sequential Garden
Landmarks and four cosmetic Cultivation Mastery ranks per species. Neither
system creates a Growth multiplier, Coin faucet, Find bonus, or extra effect
slot.

## Persistence

Mutable data stays under `ankigarden/user_files/`, which Anki preserves during
add-on upgrades. Schema 26 stores exact hundredth-Growth units, Stored Growth,
card-counted Fertilizer and Booster queues, Garden Rhythm and effect snapshots,
independent appearance/effect choices, dual environment pity, earned beds,
Landmark, Mastery, and lifetime economy aggregates. Recent UI receipts remain
bounded while permanent answer, Find, purchase, Charge, Landmark, Mastery, and
migration identities remain authoritative in SQLite. Supported schema 10–25
profiles migrate forward and failed reads or writes remain fail-closed.
Legacy Full Moon completion progress carries into the six-completion cadence
proportionally, rounded up so a positive earned remainder is not erased.

## Interface

- The Deck Browser, Overview, first-run state, and active-plant state adapt one shared preview snapshot. Its compact scenic postcard renders the static equipped Garden Decoration and pad between scenery and plants while the Garden name, nurtured-plant summary, and **Open Garden** action remain legible.
- The Nursery and Collection cottage use artwork-following hover/focus outlines and in-scene labels. Nursery opens **Plants**, **Fertilizers and boosts**, **Garden beds**, and **Garden Decorations and Scenery**; the cottage opens Collection in the existing Garden Progress window. Both work with mouse and keyboard.
- The full Garden header gives the Garden name primary title position, followed by **Garden Progress**, **Collection**, and secondary **Settings** navigation.
- Long metric values keep their normal type size; the Nurtured Plant, Anki Streak, and Garden Coin groups wrap onto two rows when their measured content no longer fits.
- The watering-can artwork remains bundled and resolvable for compact **Nurtured** badges, but Garden and preview scenes do not place it beside plants.
- Plant Story clearly separates editable plant name, species, stage, and Growth; it presents memories oldest to newest and a stage-relative **Up next** bar.
- Reviewer rewards stay inside the HUD: one active major reveal, at most two categorized result chips, an event-ID-backed remainder action, and a zero-free **This session** footer sourced from the exit Summary accumulator.
- The Reviewer safe area reserves a 296 px HUD width, 44 px from the top and
  16 px from the right, with measured answer-control clearance and a 72 px
  fallback. Narrow layouts collapse the shell before it can enter the answer
  controls.
- Collection is the collectible browser and Garden loadout manager. It derives categories from the registry, distinguishes explicit mysteries from ordinary locked items, manages plant placement, and owns reversible previews plus atomic equipment and visibility changes.
- Production Settings keeps only the applicable display/notification choices,
  including **Reduce animations**, **Show reviewer HUD**, **Show reviewer
  rewards**, and default-on **Show rewards after syncing**. The sync setting
  changes receipt presentation only; imported rewards are still processed.
  Settings uses automatically balanced artwork and presents read-only
  **Diagnostics** separately. Backup, populate, and restore controls exist only
  in an explicitly built capture package and are absent from the distributable.

## Runtime bundle

The distributable contains one current art line instead of retaining every
development generation:

- one canonical Verdant Twilight V6 responsive environment plus eight compatible Scenery reskins with unchanged masks, anchors, path, Nursery, and cottage;
- one approved transparent, pixel-lossless WebP for each of 10 species across 6 Growth stages;
- seven standardized Garden Bonus masters plus one reusable stone pad, eight
  Display Decoration assets, six Landmark assets, and four reusable Mastery
  overlays. Legacy Weather ownership migrates without requiring legacy visual
  assets.

V2–V5 scene and plant alternatives, migration-only catalogs, draft review
assets, and the packaged placeholder bitmap are excluded. Missing or unreadable
art does not alter saved plants or progression: the UI keeps the plant's name
and stage and draws its code-native fallback. The package tests enforce the
current-only file set and the release archive size ceiling for the complete
Scenery, Garden Decoration, plant, planter, and UI asset library.

The accepted file count, byte size, and SHA-256 are recorded from the final
rebuilt archive only after the exact-package tests and complete UI capture pass.

## Validation boundary

Automated ownership, geometry, package, and isolated-startup checks do not prove
native macOS full-screen behavior. Release acceptance must still open the Garden
and its nested dialogs from a full-screen Anki window and confirm that no action
switches Spaces or creates a stray top-level window. A capture report whose
`quality_status` remains `review-required` or whose `release_ready` value is
`false` is review evidence, not release approval.

The [canonical 2.1.0 UI evidence record](docs/ui/final-ui-audit-2.1.0.md)
remains frozen historical evidence for the merged UI prerequisite. It does not
approve the 2.2.0 economy candidate. Fresh exact-package evidence and the
remaining native, platform, accessibility, and human gates stay required.

## Diagnostics

- **No plant is selected:** Growth from completed cards is stored. Choose an unfinished plant to apply it; nothing already earned is lost.
- **Artwork cannot be loaded:** saved plants and progression remain intact. The affected surface keeps the plant name and stage and uses a code-native fallback until the packaged resource is available again.
- **The add-on does not appear after a source install:** confirm that `ankigarden/` is inside Anki's `addons21` directory, then restart Anki. The installed folder must include `manifest.json`, the Python package, and the manifest-owned assets.
- **A development package fails validation:** run the commands in [Development checks](#development-checks) from the repository root. Asset-audit or source/archive-parity failures should be fixed before installing or distributing the archive.

For a release smoke test, use a fresh disposable Anki base and profile with sync
disabled. Do not test an unpublished build against a normal collection merely
to confirm startup.

## Install from source

Copy or symlink `ankigarden/` into Anki’s `addons21` directory, then restart Anki. Open the Garden from its Deck Browser or Overview card. Open settings from **Caleb M. Add-ons Settings → Anki Garden settings**.

Build the deterministic production package with:

```bash
./.venv/bin/python scripts/package_addon.py --production
```

The artifact is atomically validated and written to
`dist/anki_garden.ankiaddon`. It excludes the capture harness and fixes all
development-mutation capabilities off. The complete `ankigarden/capture/`
subtree is capture-only. A UI-capture package must be requested explicitly and
written to a different path:

```bash
./.venv/bin/python scripts/package_addon.py --capture \
  --output build/ui-face-captures/anki_garden_capture.ankiaddon
```

Capture builds cannot overwrite the production artifact.

## Development checks

```bash
# Fast feedback (the default):
./.venv/bin/pytest -q

# Slower package, capture, artwork, and live-Qt release evidence:
./.venv/bin/pytest -q -o addopts='' -m release_evidence

# Explicit union of both lanes:
./.venv/bin/pytest -q -o addopts=''

# Non-mutating v26 capture diagnostics and registry inspection:
./.venv/bin/python scripts/capture_sequence.py --doctor
./.venv/bin/python scripts/capture_sequence.py --list-surfaces
./.venv/bin/python scripts/capture_sequence.py --plan-only --profile representative

# Incremental representative preflight, full release capture, or isolated shutdown gate:
./.venv/bin/python scripts/capture_sequence.py --profile representative
./.venv/bin/python scripts/capture_sequence.py --profile full
./.venv/bin/python scripts/capture_sequence.py --gate-only

PYTHONPYCACHEPREFIX=/private/tmp/anki-garden-pycache ./.venv/bin/python -m compileall -q ankigarden scripts tests
./.venv/bin/python scripts/audit_assets.py
./.venv/bin/python scripts/package_addon.py --production
python3 -m zipfile -t dist/anki_garden.ankiaddon
git diff --check
```

### Optional runtime performance tracing

The production package includes a bounded timing recorder that is disabled by
default and never changes learner behavior. Before launching a sync-disabled
disposable Anki profile, set both variables below to collect at most 256 samples
per operation and write median, p95, and maximum timings at clean shutdown:

```bash
ANKI_GARDEN_PERF_TRACE=1
ANKI_GARDEN_PERF_OUTPUT=/absolute/path/runtime.json
```

Summarize one run, or compare it with an earlier trace, from the repository
root:

```bash
./.venv/bin/python scripts/profile_runtime.py /absolute/path/runtime.json
./.venv/bin/python scripts/profile_runtime.py /absolute/path/runtime.json \
  --baseline /absolute/path/baseline.json
```

Capture contract and orchestration tests are deliberately small and Qt-free;
the real exact-package Qt/WebView, shutdown, manifest, and contact-sheet
proof is produced by the repository capture command instead of simulated by a
large pytest matrix. The fast and release-evidence lanes are kept compact, while
the explicit union is the complete local check. CI gives the fast lane a
120-second outer timeout and each independently scheduled release-evidence
shard a 60-second timeout.

The runtime target is Anki 25.07 through 26.08. Release acceptance installs the exact rebuilt archive into a separately keyed, disposable Anki 26.08 base/profile with sync disabled.

The full product and QA contracts are in [`docs/feature-evidence-matrix.md`](docs/feature-evidence-matrix.md), [`docs/ui/data_contracts.md`](docs/ui/data_contracts.md), and [`docs/ui/state_scenarios.md`](docs/ui/state_scenarios.md).
