# Anki Garden 🌿

Anki Garden is a calm, local-first Anki add-on that turns completed cards into a growing hand-painted garden.

> Cards complete → Growth → plant stages
>
> Today’s Cards, streak rewards, achievements, plant stages, and Garden Finds → rewards → plants, supplies, scenery, and decorations in the Shop

For exact current Growth, reward, consumable, Garden Decoration, Scenery, Garden Find,
achievement, and economy rules, see the
[progression, rewards, and effects reference](docs/progression-rewards-effects-reference.md).
The integrated working-tree candidate is Anki Garden 2.2.0; its learner-visible
changes and migration boundary are summarized in the
[2.2.0 release notes](docs/release-notes-2.2.0.md).

## Current release highlights

- The 2.2.0 economy uses state schema 27, card-counted consumables, earned beds,
  Garden Cycle rewards, and renderer-neutral projections for purchases,
  balances, committed rewards, and long-term Growth projects.
- Garden Landmark, per-species Cultivation Mastery, and Garden Legacy provide
  optional cosmetic long-term goals without adding a second currency or
  changing ordinary card Growth.
- A clearer first-run path explains that plant Growth and repeatable rewards begin
  after the learner chooses and nurtures a starter and are not backfilled;
  reliably reconstructable one-time achievements are handled separately from
  authoritative review history.
- Home, Garden, Collection, Shop, Progress, Settings, plant details, and reviewer notices now share consistent learner-facing copy, accessible focus states, control sizing, and reduced-motion behavior.
- Native controls now share one semantic theme, DPR-aware icon cache, and visible
  switch-state treatment, keeping interaction geometry and state feedback
  consistent across Settings, Progress, Collection, Shop, and
  transaction dialogs.
- The fixed-height Home preview keeps the garden name, nurtured plant, Growth, and **Open Garden** visible without duplicating Today’s Cards, Anki streak, or Garden Coins; the full Garden provides the richer progression and interaction detail.
- Native dialogs now fit their visible state, use one deliberate overflow owner, normal-flow feedback and footers, text-fit button sizes, and compact left-accent status banners. Every add-on window now uses a native parented dialog, and visibility-sensitive controls receive parents before they can be shown; an opt-in audit can report unexpected parentless windows without creating native handles.
- The Garden uses one 1040 × 720 window with persistent Garden, Collection, Shop, and Progress tabs. The scene adapts to its available space and keeps the existing scenery composition without stretching; selecting another tab does not resize the window.
- Reviewer progression stays inside one compact, content-driven HUD. Routine answers update the plant and session totals in place; meaningful committed rewards use one integrated reveal and one correlation-bound bundle rather than detached toast cards.
- Steady-state review maintenance reuses only an unchanged scheduler-day, review-history, and ledger signature. Proven local card completions use a narrow bounded lookup when safe, while sync, undo, collection reload, or ambiguity invalidates that proof and restores the complete fail-closed reconciliation path.
- Hidden progress pages render lazily, wall-time refresh timers run only while visible timed status exists, static scene animation timers stop, and bounded per-widget caches reuse scene layout and raster work without changing learner state.
- Runtime artwork now uses manifest-owned, pixel-lossless WebP files while preserving the approved V6 geometry, masks, transparent edges, and code-native missing-art fallbacks.
- Runtime asset checks use bounded container reads and a path/size/mtime cache, avoiding repeated multi-megabyte reads and ordinary metadata writes without changing selection or fallback behavior.
- Capture contract v27 compiles the current single-window routes into 18 representative and 36 full surfaces, shown on two and five contact sheets. Each surface binds its fixture, scenario, source-package digest, geometry, and native pixels. Historical v25/v26 evidence stays frozen. Captures use a uniquely identified disposable Anki profile with sync disabled, restore fixtures between surfaces, and record clean shutdown. Validation checks visible content, clipping, scroll ownership, meaningful actions, and package parity; retired widget-order and size snapshots do not define the redesigned UI.

## Gameplay terms

| Term | What it means | Gameplay effect |
|---|---|---|
| **Completed card** | Finishing a card or learning step that Anki Garden can count. | Gives the unfinished plant you nurture **10 base Growth**. Again, Hard, Good, and Easy give equal ordinary Growth. |
| **Nurture** | Choose which unfinished plant receives future Growth. | Switching plants never moves Growth already earned. |
| **Growth** | A plant's progress toward its next visual stage. | Unlocks Seed, Sprout, Young, Mature, Flowering, and Full Bloom stages. |
| **Answer Growth** | Growth calculated when a card is completed. | Combines 10 base Growth with Garden Rhythm, Fertilizer, Potion, the active Garden Bonus, and Scenery Effect. Each other planted bed creates a separate 10% Shared Growth lane. |
| **Instant Growth** | A fixed Growth reward from Finds, Growth Charges, or completion effects. | Uses no card modifiers and is not shared, but overflow is redirected or stored instead of lost. |
| **Garden Rhythm** | Verified Today’s Cards completions among the prior seven eligible study days. | Adds 0–10% to the 10 base Growth without a total-reset cliff. |
| **Anki streak** | Anki days in a row with at least one eligible card completed. | Remains visible for recurring Garden Coins and streak achievements, but no longer multiplies Growth. The first eligible answer each active day grants 4 Garden Coins; every seventh day grants 10 Coins. |
| **Today’s Cards** | The live collection-wide cards and learning steps that must be finished before Anki's cutoff. | Completing them grants 8 Garden Coins and any snapshotted completion effects. Every fifth valid completion also grants the automatic 30-Coin Garden Cycle reward. |
| **Garden Coins** | A separate spendable reward recorded in the reward and transaction ledgers. | Earned from daily study, streak rewards, achievements, Today’s Cards, plant milestones, environment effects, and Garden Finds; spent on Shop purchases and funded Landmark or Mastery claims. |
| **Garden Find** | A deterministic chance after an eligible, newly processed card, with protection from long gaps and a daily limit. | Can grant Garden Coins, Instant Growth, a consumable, or an unowned Garden Decoration or Scenery item. |
| **Fertilizer** | A card-counted bonus to Answer Growth. | Adds `+1` for 100, `+2` for 200, or `+3` for 400 eligible cards. Time outside Anki never consumes purchased value, and different tiers queue in FIFO order. |
| **Booster Potion** | A rare, non-purchasable study gift kept in your collection. | Adds `+5` Growth for the next 100 applicable cards and stacks with Fertilizer. |
| **Growth Charge** | A stored one-use supplement applied to any owned, planted, unfinished plant. | Adds `+100`, `+500`, or `+2,000` Instant Growth. Any excess is redirected or stored. |
| **Garden Decoration** | One small prop equipped in the fixed front-left Decoration bay. | Supplies one Garden Bonus. Its artwork can be hidden without disabling the bonus. |
| **Scenery** | One equipped reskin of the world around the fixed V6 garden. | Changes the setting and adds a passive without moving plants, Nursery, cottage, or path. |

## Progression details

- Every eligible completed card calculates the nurtured plant’s base Growth and all active modifiers exactly once. The nurtured plant receives the full result.
- Every other planted plant creates an exact 10% Shared Growth lane. A plant
  still growing receives its own share. A Full Bloom plant’s share is divided
  exactly among the planted plants still growing, including the nurtured plant.
  Fractions are preserved.
- Six planted beds therefore produce 150% total garden output while at least one
  plant remains unfinished.
- Garden Rhythm applies 0%, 2%, 4%, 6%, 8%, or 10% to base Growth according
  to verified Today’s Cards completions among the prior seven eligible study
  days. The Anki streak remains a Garden Coin and achievement track.
- Plants use Seed, Sprout, Young, Mature, Flowering, and player-facing **Full Bloom** stages. The thresholds are `0`, `400`, `2,000`, `6,000`, `15,000`, and `35,000` Growth.
- Shared progression projections preserve internal `rare` state while displaying **Full Bloom**. Compact status identifies both stage and position, for example `Sprout · 2 of 6 stages`.
- Each stage pool pays at 25%, 50%, 75%, and completion. Full Bloom also grants one Small Growth Charge, a permanent collection record, and automatic continuation to the next planted unfinished plant.
- Growth never disappears at a plant cap or when no plant is selected. It
  continues to another eligible plant or enters Stored Growth. After the first
  Full Bloom, final overflow can fund one acknowledged Landmark, Mastery, or
  Legacy target; without an active target it remains Stored Growth.
- After activation, each eligible newly processed card independently checks the
  Standard and unowned-environment Garden Find pools. The Standard daily cap is
  3 below 200 eligible answers, 4 from 200–399, and 5 at 400 or more. A Standard
  Find and an environment discovery may stack with other rewards from the same
  card.
- Standard Find Growth is Instant Growth. It receives no streak or card modifier and is not shared. If no plant can receive it, the complete value enters Stored Growth.

## Anki-day reward rules

An Anki day follows Anki's configured next-day cutoff. The first eligible
completed card starts or continues the streak and grants 4 Garden Coins.

Every seventh active-streak day grants 10 Garden Coins. One-time achievements
may stack with recurring rewards. Completing **Today’s Cards** grants 8 Garden
Coins plus any snapshotted Garden Bonus or Scenery Effect completion gift. The
first valid completion also unlocks the one-time 5-Coin Review Day achievement.
Every fifth valid completion adds the automatic 30-Coin Garden Cycle reward;
missing days do not reset that cycle. A single learner-facing result groups
every reward produced by the same completed card.

Today’s Cards uses a live collection-wide check at the moment of completion. It includes:

- new and review cards exposed by Anki’s active deck limits, including active filtered decks;
- learning and relearning steps due before Anki's next-day cutoff;
- cards restored from suspended or buried state before the award, if they are then due.

Scheduler-available new cards count from the start; moving one into Learning does not mark it complete. Cards remain excluded while suspended or buried. At least one eligible card must be completed, the reward can be earned once per Anki day, and it is never revoked after being granted.

The compact HUD keeps Today's Cards globally scoped. In progress it emphasizes
the number left alongside reviewed/starting progress. Completion becomes `All
cards complete`, the exact Coin reward, and `176 reviewed today`. Find caps,
pity state, `Daily limit reached`, and an `ALL DECKS` control are never persistent
Reviewer copy.

Card and Growth breakdowns remain available in **Details**. Session totals stay
distinct from daily totals, and the summaries use committed reward amounts.

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
- Click selects a plant in the compact bottom inspector: its name, stage, progress, and Nurture, Use item, Move, and Details actions.
- Click outside or press Escape to dismiss. The inspector stays in place and updates when another plant is selected.
- Move highlights valid garden spaces. Click or keyboard-select one to save immediately, then use the inline Undo action if needed; Escape cancels before placement.
- Overlap hit testing follows depth order, and geometry-v2 `interaction_bounds` keep transparent artwork margins from stealing clicks.

One Garden window keeps **Garden**, **Collection**, **Shop**, and **Progress** visible throughout. The coin balance opens **Progress → Coins**; the gear opens Settings. Plant-specific information stays in the inspector and **Plant details**.

The nursery building opens **Shop** and the cottage opens **Collection** in that same window. During placement, the scene keeps the chosen plant and available beds visible. First run offers four free starter choices inline, then asks where to plant the selection and which plant to nurture. Garden naming is optional in Settings; an unnamed garden is **My Garden**.

**Collection** has **Plants**, **Scenery**, **Decorations**, and **Landmarks**. **Shop** has **Plants**, **Supplies**, **Scenery**, and **Decorations**. **Progress** has **Today**, **Achievements**, and **Coins**; Today combines daily cards, the streak calendar, and the next bed unlock. Detailed reward rules are behind **Details**.

## Fertilizer and collection

- Basic Fertilizer: 30 Garden Coins, `+1` Growth for the next 100 eligible cards.
- Quality Fertilizer: 100 Garden Coins, `+2` Growth for the next 200 eligible cards.
- Magical Fertilizer: 300 Garden Coins, `+3` Growth for the next 400 eligible cards.

Fertilizer is card-counted and never expires with wall-clock time. Reusing the
same tier adds cards. A different tier queues behind the current tier in FIFO
order. Up to five doses may be active or queued on a plant; a rejected dose
remains in inventory. At Full Bloom, remaining cards transfer to the next
eligible nurtured plant or wait until a valid target is chosen.

Booster Potions are not sold. A Garden Find can add one to the collection; using
it grants `+5` Growth for the next 100 applicable cards. Herbalist’s Hourglass
changes that to 125 cards when the Potion is activated. Full Moon Garden may
award Potions but does not extend them. Potions stack with Fertilizer, and using
another Potion extends the remaining card count.

Small and Standard Growth Charges can be bought repeatedly for 30 and 125
Garden Coins. They add 100 and 500 Instant Growth. The 2,000-Growth Grand
Charge is earned through Botanical Collection, Old Growth, and major rewards.
A Charge can target any owned, planted,
unfinished plant from the inspector's **Use item** action.
Confirmation revalidates the target, inventory, Growth, reward terms, and
request identity; it receives no card modifiers and is not shared. Overflow is
redirected or stored. Normal milestone and Coin rewards still apply. A failed save restores Growth,
inventory, rewards, feedback, and the replay ledger.

## Garden Decorations, Scenery, and Garden Finds

Exactly one owned Garden Decoration may be displayed, and one owned decoration
supplies the Garden Bonus. Those choices may differ. One Scenery remains active,
and the displayed Scenery may differ from the active Scenery Effect. The two
mechanical choices stack.
The Shop sells one-time purchases and keeps owned items in Collection. Selecting owned scenery or a decoration applies its appearance immediately, with **Undo**. The separate **Use bonus today** or **Use bonus tomorrow** action controls its mechanical effect. Turning off artwork does not disable that effect. Undiscovered Find-only artwork remains a silhouette.
Garden Rhythm, the Garden Bonus, and the Scenery Effect snapshot together on
the first eligible answer of the Anki day. Later mechanical changes queue for
the next Anki day and cannot rewrite committed results. Displayed appearance
may change at any time. Separate
visibility switches hide either visual layer without disabling its effect.

See the [illustrated Garden Decorations reference](docs/references/garden-decorations-reference.docx)
for the complete visual catalog and effect summary.

Garden Decorations and Scenery stay within a bounded daily power budget. Completion gifts
trigger only when Today’s Cards is complete, not from opening the reviewer or
completing a single card. Each gift has its own durable reward identity and does
not suppress either Garden Find pool.

| Garden Decoration | Acquisition | Garden Bonus |
|---|---|---|
| Seedling Sign | Included | None |
| Wind Chime | Shop: 100 Coins | Every 10 eligible answers, +1 Growth; the remainder persists across days |
| Harvest Bell | Shop: 175 Coins | +5 Garden Coins when Today’s Cards is complete |
| Watering Station | Shop: 250 Coins | Every fifth eligible answer among the first 100 of the day, +1 Growth |
| Herbalist’s Hourglass | Shop: 350 Coins | Every 30 active completions, gain one Booster Potion; activated Potions receive 25 extra cards |
| Firefly Lantern | Rare environment discovery | Every fifth eligible answer, +3 Instant Growth to the unfinished planted plant closest to its next checkpoint |
| Prism Trellis | Very Rare environment discovery | Banks 1 Growth for each of the first 100 eligible cards per day, up to 300; releases the bank when Today’s Cards is complete |

The Standard Find pool contains Garden Coin awards, 40/60/100 Instant Growth,
Small and Standard Growth Charges, Basic Fertilizer (shown as **Rich Compost**),
a Booster Potion, and the exceptional 40-Coin Garden Treasury. The full Garden
may explain the cap, protection, and guarantee; the persistent Reviewer HUD
shows a Find only when it is earned and never exposes those counters. The
independent environment
tiers use base chances of `1 in 2,500`, `1 in 10,000`, and `1 in 25,000`, with
card guarantees at 10,000, 40,000, and 50,000 eligible cards respectively,
plus independent guarantees at 60, 180, and 365 valid Today’s Cards
completions.

The configured roster contains ten direct-soil species—Bonsai, Rose, Sunflower,
Lavender, Hydrangea, Peony, Foxglove, Japanese Maple, Wisteria, and Dahlia—and
up to six garden beds. The Shop lists a species only after its complete
six-stage Verdant Twilight line is release-ready; all ten configured species
are ready in the current bundle. Existing owned species remain usable even when
they are not currently stocked. Moving a plant to Collection preserves its
Growth and story. Any one starter is free, and every later current-species
purchase costs 250 Garden Coins. Beds 1–2 are included; Beds 3–6 are earned when
the first plant reaches Mature and when one, three, and six unique species reach
Full Bloom.

Collection shows the number of plant species discovered. Scenery, Decorations, and Landmarks have their own tabs; combined catalog-entry counters are omitted.

| Species | Later purchase |
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

## Persistence

Mutable data stays under `ankigarden/user_files/`, which Anki preserves during
add-on upgrades. Schema 27 stores exact hundredth-Growth units, Stored Growth,
card-counted Fertilizer and Booster queues, Garden Rhythm and daily economy
snapshots, independent appearance/effect choices, dual environment pity,
earned beds, Garden Cycle, active Growth targets, cumulative Landmark and
Mastery funding and claims, Garden Legacy, and the durable pending sync-reward
receipt. Permanent answer, Find, discovery, purchase, Charge, project, and
migration identities remain independent from bounded UI history. Supported
schema 10–26 profiles migrate forward; schema-21 JSON and SQLite profiles are
backed up at their historical migration boundary. Failed reads or writes remain
fail-closed.

## Interface

- The Deck Browser, Overview, first-run state, and active-plant state adapt one shared preview snapshot. Its compact scenic postcard renders the static equipped Garden Decoration and pad between scenery and plants while the Garden name, nurtured-plant summary, and **Open Garden** action remain legible.
- Garden, Collection, Shop, and Progress use one persistent window, with compact tabs and a shared garden-green palette. The default window is 1040 × 720 and clamps to the available screen.
- Ordinary actions are 28–34 px high. Catalog artwork uses selection tiles; buying and using items uses compact row actions.
- The bottom plant inspector leaves the garden visible. **Use item** groups owned Fertilizer and Growth Charges for the selected plant; **Shop supplies** keeps that plant selected.
- **Plant details** shows the editable name, species, growth stages, next-stage progress, and memories when present.
- Reviewer rewards stay inside the HUD: one active major reveal, at most two categorized result chips, an event-ID-backed remainder action, and a zero-free **This session** footer sourced from the exit Summary accumulator.
- The Reviewer safe area reserves a 296 px HUD width, 44 px from the top and
  16 px from the right, with measured answer-control clearance and a 72 px
  fallback. Narrow layouts collapse the shell before it can enter the answer
  controls.
- Collection separates owned plants, scenery, decorations, and landmarks. Appearance changes support Undo and remain independent of today’s active bonus.
- Production Settings keeps only the applicable display/notification choices,
  including **Reduce animations**, **Show reviewer HUD**, **Show reviewer
  rewards**, and default-on **Show rewards after syncing**. The sync setting
  changes receipt presentation only; imported rewards are still processed.
  Settings presents read-only **Diagnostics** in a collapsed disclosure. Backup, populate, and restore controls exist only
  in an explicitly built capture package and are absent from the distributable.

## Runtime bundle

The distributable contains one current art line instead of retaining every
development generation:

- one canonical Verdant Twilight V6 responsive environment plus eight compatible Scenery reskins with unchanged masks, anchors, path, Nursery, and cottage;
- one approved transparent, pixel-lossless WebP for each of 10 species across 6 Growth stages;
- eight Garden Bonus/environment assets, eight Display Decoration cosmetics,
  six Garden Landmark artworks, four Mastery treatments, and the reusable UI
  assets required by the current scenes. Legacy Weather ownership migrates
  without requiring legacy visual assets.

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

The September 4 redesign passed the focused UI/package checks and all **36 native
capture surfaces**, with **five validated contact sheets**. Review the current
[contact-sheet index](build/ui-face-captures/full/contact-sheets/anki-garden-ui-contact-sheet-2.2.0-20260904-173751/contact-sheet-set.json),
[capture report](build/ui-face-captures/full/capture-sequence-20260904-173751/capture-report.json),
and [implementation and verification report](docs/ui/ui-redesign-2.2.0.md).
These captures used Anki 26.8.1 on the primary macOS display at 100% Qt scale.
The candidate remains `review-required` pending human release acceptance.

The [September 1 contact-sheet set](build/ui-face-captures/full/contact-sheets/anki-garden-ui-contact-sheet-2.2.0-20260901-002050/contact-sheet-set.json)
and [earlier 2.2.0 audit](docs/ui/final-ui-audit-2.2.0.md) are preserved as the
redesign's historical baseline. The current navigation, UI changes, package,
and validation results are documented in the
[2.2.0 redesign report](docs/ui/ui-redesign-2.2.0.md).

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

# Non-mutating v27 capture diagnostics and registry inspection:
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
