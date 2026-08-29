# Anki Garden 🌿

Anki Garden is a calm, local-first Anki add-on that turns completed cards into a growing hand-painted garden.

> Cards complete → Growth → plant stages
>
> Today’s Cards, streak rewards, achievements, plant stages, and Garden Finds → rewards → Nursery plants, spaces, supplements, Garden Features, and Scenery

For exact current Growth, reward, consumable, Garden Feature, Scenery, Garden Find,
achievement, and economy rules, see the
[progression, rewards, and effects reference](docs/progression-rewards-effects-reference.md).

## Current release highlights

- A clearer first-run path explains that plant Growth and repeatable rewards begin
  after the learner chooses and nurtures a starter and are not backfilled;
  reliably reconstructable one-time achievements are handled separately from
  authoritative review history.
- Home, Garden, Nursery, Garden Progress, Settings, plant cards, and reviewer notices now share consistent learner-facing copy, accessible focus states, control sizing, and reduced-motion behavior.
- Native controls now share one semantic theme, DPR-aware icon cache, and visible
  switch-state treatment, keeping interaction geometry and state feedback
  consistent across Settings, Garden Progress, Collection, Nursery, and
  transaction dialogs.
- The fixed-height Home preview keeps the garden name, nurtured plant, Growth, and **Open garden** visible without duplicating Today’s Cards, Anki streak, or Garden Coins; the full Garden provides the richer progression and interaction detail.
- Native dialogs now fit their visible state, use one deliberate overflow owner, normal-flow feedback and footers, text-fit button sizes, and compact left-accent status banners. Every add-on window now uses a native parented dialog, and visibility-sensitive controls receive parents before they can be shown; an opt-in audit can report unexpected parentless windows without creating native handles.
- The full Garden uses one centered 1260 × 840 (3:2) release canvas. Existing 4:3 scenery art covers that canvas at 50% 48%, preserving horizontal composition and cropping vertically without stretching.
- Reviewer progression stays inside one compact, content-driven HUD. Routine answers update the plant and session totals in place; meaningful committed rewards use one integrated reveal and one correlation-bound bundle rather than detached toast cards.
- Steady-state review maintenance reuses only an unchanged scheduler-day, review-history, and ledger signature. Proven local card completions use a narrow bounded lookup when safe, while sync, undo, collection reload, or ambiguity invalidates that proof and restores the complete fail-closed reconciliation path.
- Hidden progress pages render lazily, wall-time refresh timers run only while visible timed status exists, static scene animation timers stop, and bounded per-widget caches reuse scene layout and raster work without changing learner state.
- Runtime artwork now uses manifest-owned, pixel-lossless WebP files while preserving the approved V6 geometry, masks, transparent edges, and code-native missing-art fallbacks.
- Runtime asset checks use bounded container reads and a path/size/mtime cache, avoiding repeated multi-megabyte reads and ordinary metadata writes without changing selection or fallback behavior.
- Capture contract v25 compiles one Qt-free surface registry into an immutable manifest. The current representative/full profiles contain 17/33 structurally distinct surfaces and two/five generated sheets, including the clean content-driven Reviewer HUD, its seven-event integrated reward bundle, the post-review Session Summary, and the full profile's default Today’s Cards page. Removed or behavioral-only IDs remain permanently reserved, including the retired starter-confirmation and detached Reviewer-stack IDs. No watering-can surface is active. Native dialogs use fail-closed `QWidget.grab()` acquisition; Home and Reviewer prefer a verified app-owned Qt/WebView image and permit a compositor fallback only after exact process, window, geometry, DPR, semantic identity, overlay, and crop checks. Visual telemetry independently recomputes Web-root overflow, visible-action containment and overlap, first-fold card geometry, Growth Charge carryover, HUD geometry, reward-dock containment, bundle composition, and session-footer identity rather than trusting renderer pass flags. Only gross acquisition or lifecycle defects reject a PNG; detailed semantic, copy, layout, scroll, and duplicate-view audits remain visible review advisories. A normal profile opens one disposable Anki process, captures every selected surface with checkpoint restoration between surfaces, and records clean shutdown from that same process. Memory-leak probing is not part of capture.

## Gameplay terms

| Term | What it means | Gameplay effect |
|---|---|---|
| **Completed card** | Finishing a card or learning step that Anki Garden can count. | Gives the unfinished plant you nurture **10 base Growth**. Again, Hard, Good, and Easy give equal ordinary Growth. |
| **Nurture** | Choose which unfinished plant receives future Growth. | Switching plants never moves Growth already earned. |
| **Growth** | A plant's progress toward its next visual stage. | Unlocks Seed, Sprout, Young, Mature, Flowering, and Full Bloom stages. |
| **Answer Growth** | Growth calculated when a card is completed. | Combines 10 base Growth with the streak, Fertilizer, Potion, the active Garden Bonus, and Scenery. Each other planted bed creates a separate 20% Shared Growth share. |
| **Instant Growth** | A fixed Growth reward from Finds, Growth Charges, or completion effects. | Uses no card modifiers and is not shared, but overflow is redirected or stored instead of lost. |
| **Anki streak** | Anki days in a row with at least one eligible card completed. | Gives 0% Growth at day 1, then +5%, +10%, +15%, +20%, and +25% at days 7, 14, 30, 100, and 365. The first completed card each active day grants 2 Garden Coins; every seventh day grants 10 Coins. |
| **Today’s Cards** | The live collection-wide cards and learning steps that must be finished before Anki's cutoff. | Completing them grants 10 Garden Coins and the locked Scenery completion gift. |
| **Garden Coins** | A separate spendable reward recorded in the reward and transaction ledgers. | Earned from daily study, streak rewards, achievements, Today’s Cards, plant milestones, environment effects, and Garden Finds; spent in the Nursery. |
| **Garden Find** | A deterministic chance after an eligible, newly processed card, with protection from long gaps and a daily limit. | Can grant Garden Coins, Instant Growth, a consumable, or an unowned Garden Feature or Scenery item. |
| **Fertilizer** | A timed bonus to Answer Growth. | Adds `+1`, `+2`, or `+3` Growth per eligible card for one, two, or four hours. Faster review earns more value; a different tier queues without losing time. |
| **Booster Potion** | A rare, non-purchasable study gift kept in your collection. | Adds `+5` Growth for the next 100 applicable cards and stacks with Fertilizer. |
| **Growth Charge** | A stored one-use supplement applied to any owned, planted, unfinished plant. | Adds `+100`, `+500`, or `+2,000` Instant Growth. Any excess is redirected or stored. |
| **Garden Feature** | One small prop equipped in the fixed front-left Feature bay. | Supplies one Garden Bonus. Its artwork can be hidden without disabling the bonus. |
| **Scenery** | One equipped reskin of the world around the fixed V6 garden. | Changes the setting and adds a passive without moving plants, Nursery, cottage, or path. |

## Progression details

- Every eligible completed card calculates the nurtured plant’s base Growth and all active modifiers exactly once. The nurtured plant receives the full result.
- Every other planted plant creates an exact 20% Shared Growth share. A plant
  still growing receives its own share. A Full Bloom plant’s share is divided
  exactly among the planted plants still growing, including the nurtured plant.
  Fractions are preserved.
- Six planted beds therefore retain 200% total garden output while at least one
  plant remains unfinished.
- The current Anki streak adds a transparent Growth bonus: day 1 gives 0%; days 7, 14, 30, 100, and 365 unlock +5%, +10%, +15%, +20%, and +25% respectively. Missing an Anki day resets the next streak to day 1.
- Plants use Seed, Sprout, Young, Mature, Flowering, and player-facing **Full Bloom** stages. The thresholds remain `0`, `500`, `2,500`, `8,000`, `20,000`, and `50,000` Growth.
- Each stage pool pays at 25%, 50%, 75%, and completion. Full Bloom also grants one Small Growth Charge, a permanent collection record, and automatic continuation to the next planted unfinished plant.
- Growth never disappears at a plant cap or when no plant is selected. It continues to another eligible plant or enters Stored Growth until the learner chooses a plant.
- After activation, each eligible newly processed card independently checks the Standard and unowned-environment Garden Find pools. At most three Standard Finds may be earned per Anki day. A Standard Find and an environment discovery may stack with other rewards from the same card.
- Standard Find Growth is Instant Growth. It receives no streak or card modifier and is not shared. If no plant can receive it, the complete value enters Stored Growth.

## Anki-day reward rules

An Anki day follows Anki's configured next-day cutoff. The first eligible completed card starts or continues the streak and grants 2 Garden Coins.

Every seventh active-streak day grants 10 Garden Coins. One-time achievements
may stack with recurring rewards. Completing **Today’s Cards** grants 10 Garden
Coins plus the locked Scenery completion gift. The first valid completion also
grants a 5-Coin first-completion bonus. A single learner-facing result groups
every reward produced by the same completed card.

Today’s Cards uses a live collection-wide check at the moment of completion. It includes:

- review cards exposed by Anki’s active deck limits, including active filtered decks;
- introduced learning and relearning steps due before Anki's next-day cutoff;
- cards restored from suspended or buried state before the award, if they are then due.

Unseen new cards are excluded until introduced. Cards remain excluded while suspended or buried. At least one eligible card must be completed, the reward can be earned once per Anki day, and it is never revoked after being granted.

The compact HUD keeps Today's Cards globally scoped. In progress it emphasizes
the number left alongside reviewed/starting progress. Completion becomes `All
cards complete`, the exact Coin reward, and `176 reviewed today`. Find caps,
pity state, `Daily limit reached`, and an `ALL DECKS` control are never persistent
Reviewer copy.

Only unseen supported card-completion records inside Anki's current `[day start, next-day
cutoff)` window are caught up after a same-day sync. A bounded persisted ID
ledger counts late out-of-order rows exactly once, including a lower ID that
arrives after a higher one. Prior-day and future/device-skew rows are neither
credited nor marked processed. If Anki's cutoff or review log is unavailable,
or saving fails, Garden defers the update without advancing its ledger and
retries later.

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
opens the Nursery when the learner chooses that action. It offers one
release-ready starter for free and begins with a second empty unlocked space.
Garden naming is optional personalization in Settings; unnamed Gardens display
**My Garden**. New plants begin with an unambiguous generated name such as
**Bonsai Plant**. The Nursery is a warm catalog with **Plants**, **Fertilizers and
boosts**, **Garden beds**, and **Garden Features and Scenery** tabs, stage artwork
previews, and item art.

## Fertilizer and collection

- Basic Fertilizer: 30 Garden Coins, `+1` Growth per eligible card for 1 hour.
- Quality Fertilizer: 100 Garden Coins, `+2` Growth per eligible card for 2 hours.
- Magical Fertilizer: 300 Garden Coins, `+3` Growth per eligible card for 4 hours.

Fertilizer uses real elapsed time, including time outside the reviewer. Reusing
the same tier extends its remaining time. A different tier queues behind the
current tier and begins only after the earlier duration ends. Up to five paid
doses may be active or queued; a rejected dose remains in inventory. At Full
Bloom, remaining Fertilizer time transfers to the automatically selected plant
or waits for the next Nurture choice when no recipient exists.

Booster Potions are not sold. A Garden Find can add one to the collection; using
it grants `+5` Growth for the next 100 applicable cards. Herbalist’s Hourglass changes
that to 110 cards, Full Moon Garden to 125, or both to 135. Potions stack with
Fertilizer.
Using another Potion extends the remaining card count.

Small and Standard Growth Charges can be bought repeatedly for 30 and 125
Garden Coins. They add 100 and 500 Instant Growth. The 2,000-Growth Grand
Charge is not currently obtainable. A Charge already present in imported
development state remains usable. A Charge can target any owned, planted,
unfinished plant from its selected-plant panel or Plant Growth card.
Confirmation revalidates the target, inventory, Growth, reward terms, and
request identity; it receives no card modifiers and is not shared. Overflow is
redirected or stored. Normal milestone and Coin rewards still apply. A failed save restores Growth,
inventory, rewards, feedback, and the replay ledger.

## Garden Features, Scenery, and Garden Finds

Exactly one Garden Feature and one Scenery may be equipped, and their effects stack.
The Nursery sells one-time Common and Uncommon choices but never auto-equips a
purchase. The Garden Progress cottage's **Garden Features and Scenery** collection tab shows the active
loadout, every effect, how each item is earned, exact drop odds, and finite
progress to each environment guarantee.
Find-only art remains a silhouette until unlocked while its rules stay visible.
Scenery locks on the first progression event of the Anki day. The Active Feature
is snapshotted at the beginning of a continuous local review session; a change
during that session applies to the next session and cannot stack. Separate
visibility switches hide either visual layer without disabling its effect.

Garden Features and Scenery stay within a bounded daily power budget. Completion gifts
trigger only when Today’s Cards is complete, not from opening the reviewer or
completing a single card. Each gift has its own durable reward identity and does
not suppress either Garden Find pool.

| Garden Feature | Acquisition | Garden Bonus |
|---|---|---|
| Seedling Sign | Included | None |
| Wind Chime | Nursery: 100 Coins | +1 Growth on the first 10 cards |
| Harvest Bell | Nursery: 175 Coins | +5 Coins when Today’s Cards is complete |
| Watering Station | Nursery: 250 Coins | +1 Growth on the first 20 cards |
| Herbalist’s Hourglass | Nursery: 350 Coins | Booster Potions apply to 10 additional cards |
| Firefly Lantern | Rare Garden Find | +5 Growth on the first 15 cards |
| Prism Trellis | Very Rare Garden Find | +100 direct Growth when Today’s Cards is complete |

The Standard Find pool contains Garden Coin awards, 40/60/100 Instant Growth,
Small and Standard Growth Charges, Basic Fertilizer (shown as **Rich Compost**),
a Booster Potion, and the exceptional 40-Coin Garden Treasury. The full Garden
may explain the cap, protection, and guarantee; the persistent Reviewer HUD
shows a Find only when it is earned and never exposes those counters. The
independent environment
tiers use base chances of `1 in 2,500`, `1 in 10,000`, and `1 in 25,000`, with
hard guarantees at 5,000, 20,000, and 50,000 eligible cards respectively.

The configured roster contains ten direct-soil species—Bonsai, Rose, Sunflower, Lavender, Hydrangea, Peony, Foxglove, Japanese Maple, Wisteria, and Dahlia—and up to six garden spaces. The Nursery lists a species only after its complete six-stage Verdant Twilight line is release-ready; all ten configured species are ready in the current bundle. Existing owned species remain usable even when they are not currently stocked. Moving a plant to Collection preserves its Growth and story. Species cost 100–600 Garden Coins, and spaces three through six cost 150, 300, 500, and 800 Garden Coins.

| Species | Garden Coins |
|---|---:|
| Bonsai | 100 |
| Rose | 100 |
| Sunflower | 150 |
| Lavender | 200 |
| Hydrangea | 250 |
| Peony | 300 |
| Foxglove | 350 |
| Japanese Maple | 400 |
| Wisteria | 500 |
| Dahlia | 600 |

## Persistence

Mutable data stays under `ankigarden/user_files/`, which Anki preserves during
add-on upgrades. Schema 23 stores exact hundredth-Growth units, Stored Growth,
checkpoint and Full Bloom metadata, Today’s Cards projection state, locked and
queued daily loadouts, independent environment guarantees, timed Fertilizer
intervals/queues, and card-counted Booster batches. The canonical reward ledger
and stable processed-card identities remain authoritative. Schema-21 JSON and
SQLite profiles are backed up before
migration; failed reads or writes remain fail-closed.

## Interface

- The Deck Browser, Overview, first-run state, and active-plant state adapt one shared preview snapshot. Its compact scenic postcard renders the static equipped Garden Feature and pad between scenery and plants while the Garden name, nurtured-plant summary, and **Open garden** action remain legible.
- The Nursery and Collection cottage use artwork-following hover/focus outlines and in-scene labels. Nursery opens **Plants**, **Fertilizers and boosts**, **Garden beds**, and **Garden Features and Scenery**; the cottage opens Collection in the existing Garden Progress window. Both work with mouse and keyboard.
- The full Garden header gives the Garden name primary title position, followed by **Garden Progress**, **Collection**, and secondary **Settings** navigation.
- Long metric values keep their normal type size; the Nurtured Plant, Anki Streak, and Garden Coin groups wrap onto two rows when their measured content no longer fits.
- The watering-can artwork remains bundled and resolvable for compact **Nurtured** badges, but Garden and preview scenes do not place it beside plants.
- Plant Story clearly separates editable plant name, species, stage, and Growth; it presents memories oldest to newest and a stage-relative **Up next** bar.
- Reviewer rewards stay inside the HUD: one active major reveal, at most two categorized result chips, an event-ID-backed remainder action, and a zero-free **This session** footer sourced from the exit Summary accumulator.
- Collection is the collectible browser and Garden loadout manager. It derives categories from the registry, distinguishes explicit mysteries from ordinary locked items, manages plant placement, and owns reversible previews plus atomic equipment and visibility changes.
- Production Settings keeps only the applicable display/notification choices, including **Reduce animations** and **Show reviewer rewards**, uses automatically balanced artwork, and presents read-only **Diagnostics** separately. Backup, populate, and restore controls exist only in an explicitly built capture package and are absent from the distributable.

## Runtime bundle

The distributable contains one current art line instead of retaining every
development generation:

- one canonical Verdant Twilight V6 responsive environment plus eight compatible Scenery reskins with unchanged masks, anchors, path, Nursery, and cottage;
- one approved transparent, pixel-lossless WebP for each of 10 species across 6 Growth stages;
- seven standardized 1024 × 1024 Garden Feature masters plus one reusable stone pad. Legacy Weather ownership migrates without requiring legacy visual assets.

V2–V5 scene and plant alternatives, migration-only catalogs, draft review
assets, and the packaged placeholder bitmap are excluded. Missing or unreadable
art does not alter saved plants or progression: the UI keeps the plant's name
and stage and draws its code-native fallback. The package tests enforce the
current-only file set and the release archive size ceiling for the complete
schema-22 scenery, plant, and planter library.

The accepted file count, byte size, and SHA-256 are recorded from the final
rebuilt archive only after the exact-package tests and complete UI capture pass.

## Validation boundary

Automated ownership, geometry, package, and isolated-startup checks do not prove
native macOS full-screen behavior. Release acceptance must still open the Garden
and its nested dialogs from a full-screen Anki window and confirm that no action
switches Spaces or creates a stray top-level window. A capture report whose
`quality_status` remains `review-required` or whose `release_ready` value is
`false` is review evidence, not release approval.

The retained v25 manifests, contact sheets, package hashes, and still-open
acceptance gates are recorded in the
[current 2.1.0 UI evidence record](docs/ui/final-ui-audit-2.1.0.md).

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

# Non-mutating v25 capture diagnostics and registry inspection:
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
large pytest matrix. The fast lane, release-evidence lane, and explicit union
are each maintained below one minute on the canonical development machine. CI
shards release evidence and enforces a 60-second ceiling on the fast lane and
on each independently scheduled release-evidence shard.

The runtime target is Anki 25.07 through 26.08. Release acceptance installs the exact rebuilt archive into a separately keyed, disposable Anki 26.08 base/profile with sync disabled.

The full product and QA contracts are in [`docs/feature-evidence-matrix.md`](docs/feature-evidence-matrix.md), [`docs/ui/data_contracts.md`](docs/ui/data_contracts.md), and [`docs/ui/state_scenarios.md`](docs/ui/state_scenarios.md).
