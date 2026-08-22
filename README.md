# Anki Garden 🌿

Anki Garden is a calm, local-first Anki add-on that turns card answers into a growing hand-painted garden.

> Card answers → Growth → plant stages
>
> Daily study, seven-day streak rewards, achievements, All Clear, plant stages, and Garden Finds → rewards → Nursery plants, spaces, supplements, Weather, and Scenery

## Current release highlights

- A clearer first-run path explains that plant Growth and repeatable rewards begin
  after the learner chooses and nurtures a starter and are not backfilled;
  reliably reconstructable one-time achievements are handled separately from
  authoritative review history.
- Home, Garden, Nursery, Garden Progress, Settings, plant cards, and reviewer notices now share consistent learner-facing copy, accessible focus states, control sizing, and reduced-motion behavior.
- The Home preview keeps every garden landmark and plant space visible in a compact scenic postcard, while the full Garden provides contextual setup and nurturing guidance.
- Runtime artwork now uses manifest-owned, pixel-lossless WebP files while preserving the approved V6 geometry, masks, transparent edges, and code-native missing-art fallbacks.
- Runtime asset checks use bounded container reads and a path/size/mtime cache, avoiding repeated multi-megabyte reads and ordinary metadata writes without changing selection or fallback behavior.
- The release checks cover all 191 declared UI capture surfaces, runtime asset references, deterministic archive contents, and exact source-to-package parity.

## Gameplay terms

| Term | What it means | Gameplay effect |
|---|---|---|
| **Card answer** | Choosing an answer button on a card that Anki Garden can count, including learning and relearning steps. | Gives the unfinished plant you nurture **10 base Growth**. |
| **Nurture** | Choose which unfinished plant receives future Growth. | Switching plants never moves Growth already earned. |
| **Growth** | A plant's progress toward its next visual stage. | Unlocks Seed, Sprout, Young, Mature, Flowering, and Rare stages. |
| **Anki streak** | Anki days in a row with at least one eligible answer. | Gives 0% Growth at day 1, then +5%, +10%, +15%, +20%, and +25% at days 7, 14, 30, 100, and 365. Every active day grants 2 Garden Coins; every seventh day grants a 10-Coin reward, with the first cycle integrated into the 7-Day Anki Streak achievement. |
| **Garden Coins** | A separate spendable reward recorded in the reward and transaction ledgers. | Earned from daily study, seven-day streak rewards, achievements, All Clear, plant stages, environment effects, and Garden Finds; spent in the Nursery. |
| **Garden Find** | A deterministic chance after an eligible, newly processed answer, with drought protection and a daily limit. | Can grant Garden Coins, direct Growth to the nurtured plant, a consumable, or an unowned Weather or Scenery item. |
| **Fertilizer** | A timed bonus to the normal answer Growth calculation. | Adds `+1`, `+2`, or `+3` Growth per answer while active; the resulting award keeps normal nurtured and passive routing. |
| **Booster Potion** | A rare, non-purchasable study gift kept in your collection. | Adds `+5` Growth per answer for two hours and stacks with Fertilizer. |
| **Growth Charge** | A stored one-use supplement applied to any owned, planted, unfinished plant. | Adds `+100`, `+500`, or `+2,000` Growth immediately, capped at Rare, without study buffs or passive fan-out. |
| **Weather** | One equipped sky effect and its minor passive. | Can be shown or hidden without turning its passive off. |
| **Scenery** | One equipped reskin of the world around the fixed V6 garden. | Changes the setting and adds a passive without moving plants, Nursery, cottage, or path. |

## Progression details

- Every eligible card answer calculates the nurtured plant’s base Growth and all active modifiers exactly once. The nurtured plant receives the full post-buff result.
- Every other planted, unfinished plant receives an additional exact 20 percent of that same result. Fractions accumulate in persisted fifths instead of being discarded, and the nurtured plant never receives its own passive allocation.
- The current Anki streak adds a transparent Growth bonus: day 1 gives 0%; days 7, 14, 30, 100, and 365 unlock +5%, +10%, +15%, +20%, and +25% respectively. Missing an Anki day resets the next streak to day 1.
- Plants keep the existing Seed, Sprout, Young, Mature, Flowering, and Rare stages. The current thresholds are `0`, `500`, `2,500`, `8,000`, `20,000`, and `50,000` Growth.
- Stage-local feedback appears at 25%, 50%, 75%, and 100%. A plant that reaches Rare pauses; the learner chooses another unfinished plant to continue growing.
- The current streak and derivable one-time achievements are reconstructed from authoritative Anki history at startup and after sync. Recurring rewards, Growth, Garden Finds, and the live-only All Clear achievement are never backfilled.
- After activation, each eligible newly processed answer independently checks the Standard and unowned-environment Garden Find pools. Standard Finds start at `1 in 100`, improve after 40 and 60 misses, and are guaranteed on answer 75 of a drought; at most three Standard Finds may be earned per Anki day. Environment Finds keep their tier odds and Ultra pity, and may stack with a Standard Find and other rewards from the same answer.
- Standard Find Growth is direct Growth to the answer-time nurtured unfinished plant. It does not receive the streak modifier and does not fan out passively. Normal answer Growth keeps the separate nurtured plus exact-fifths passive allocation described above.

## Anki-day reward rules

An Anki day follows Anki's configured next-day cutoff. The first card answer on a new Anki day starts or continues the streak.

The first eligible answer of an active Anki day grants 2 Garden Coins. Every
seventh active-streak day grants 10 Garden Coins. One-time achievements use the
shared achievement registry and may stack with those recurring rewards. The
first valid all-due day also unlocks **All Clear** for 5 Garden Coins; the
ordinary all-due reward remains a separate 10 Garden Coins, plus any equipped
environment bonus. A single learner-facing result groups every receipt sharing
the same correlation identity.

“All due” uses a live collection-wide check at the moment of award, not a beginning-of-day snapshot. It includes:

- review cards exposed by Anki’s active deck limits, including active filtered decks;
- introduced learning and relearning steps due before Anki's next-day cutoff;
- cards restored from suspended or buried state before the award, if they are then due.

Unseen new cards are excluded until they are introduced. Cards remain excluded while suspended or buried. At least one eligible card answer is required, the reward can be earned once per Anki day, and it is never revoked after being granted.

Only unseen supported card answers inside Anki's current `[day start, next-day
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

The named Garden header, metric strip, and scene share one themed frame. Plant Growth, Anki streak, and Garden Coins are real buttons that open focused explanations with relative progress. **Garden Progress** reopens the last valid session page and defaults to **Plant Growth**; the cottage always opens **Collection**. Navigation is Plant Growth, Anki Streak, Garden Coins, Achievements, and Collection. Plant-specific information lives in the clicked-plant card, Plant Growth, or Plant Story.

Verdant Twilight V6 uses six direct-soil beds across three staggered perspective
bands. The nursery entrance is a keyboard-accessible landmark that opens the
Nursery from the full Garden, is disabled while moving a plant, and is not exposed
in the home preview. A fresh garden presents starter setup in the Garden and
opens the Nursery when the learner chooses that action. It offers one
release-ready starter for free and begins with a second empty unlocked space.
Garden naming is optional personalization in Settings; unnamed Gardens display
**My Garden**. New plants begin with an unambiguous generated name such as
**Bonsai Plant**. The Nursery is a warm catalog with **Plants**, **Fertilizer and
Boosters**, **Garden Spaces**, and **Weather and Scenery** tabs, stage artwork
previews, and item art.

## Fertilizer and collection

- Basic Fertilizer: 25 Garden Coins, `+1` Growth per answer, 1 hour.
- Quality Fertilizer: 65 Garden Coins, `+2` Growth per answer, 2 hours.
- Magical Fertilizer: 150 Garden Coins, `+3` Growth per answer, 4 hours.

Fertilizer adds to the normal answer Growth calculation only while its real
elapsed-time activation interval is active. The full result goes to the
answer-time plant you nurture and each other eligible planted plant receives its
usual exact 20 percent. The choice card shows cost,
effect, and duration. Extending the same active tier keeps one continuous
interval. Replacing a different active tier requires confirmation and discards
its remaining time, but the completed portion is retained so a late same-day
sync still receives the tier active when answered. An expired interval is also
retained when Fertilizer is purchased again; answers before activation or at or
after expiry receive no Fertilizer Growth.

Booster Potions are not sold. A Garden Find can add one to the collection; using it
on the nurtured unfinished plant grants `+5` Growth per eligible answer for two
hours. It stacks with Fertilizer, and using another Potion extends the active
Booster Potion rather than discarding its remaining time.

Small and Standard Growth Charges can be bought repeatedly for 30 and 125
Garden Coins. They add 100 and 500 Growth immediately. The 2,000-Growth Grand
Charge is not currently obtainable. A Charge already present in imported
development state remains usable. A Charge can target any owned, planted,
unfinished plant from its selected-plant panel or Plant Growth card.
Confirmation revalidates the target, inventory, Growth, reward terms, and
request identity; it applies only to that plant without passive fan-out or study
buffs. Normal stage and Coin rewards still apply. A failed save restores Growth,
inventory, rewards, feedback, and the replay ledger.

## Weather, Scenery, and Garden Finds

Exactly one Weather and one Scenery may be equipped, and their passives stack.
The Nursery sells one-time Common and Uncommon choices but never auto-equips a
purchase. The Garden Progress cottage's **Weather and Scenery** collection tab shows the active
loadout, every effect, how each item is earned, exact drop odds, and Ultra pity.
Find-only art remains a silhouette until unlocked while its rules stay visible.
Separate visibility switches hide either visual layer without disabling its
equipped passive.

Weather passives remain deliberately small: limited daily Growth, a small
all-due bonus, or a modest Booster Potion duration extension. Scenery can be
stronger, including one daily gift after an eligible answer. That gift has its
own durable reward identity and does not suppress either Garden Find pool.

The Standard Find pool contains Garden Coin awards, 40/60/100 direct Growth,
Small and Standard Growth Charges, Basic Fertilizer (shown as **Rich Compost**),
a Booster Potion, and the exceptional 40-Coin Garden Treasury. Selection is
registry-driven after the current drought chance succeeds. The independent
environment pool tests unowned items rarest-first at `1 in 100,000`,
`1 in 20,000`, and `1 in 5,000`. Ultra odds improve in steps after 75,000
misses to a maximum `1 in 50,000`; there is no guarantee, and only an Ultra
environment resets that pity counter.

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
add-on upgrades. The current state is schema 21. It retains exact per-plant
passive fifths and daily source/allocation accounting, and adds the canonical
reward event ledger, grouped receipts, stable processed-answer identities,
achievement reconstruction/finalization markers, Garden Find drought and daily
counts, bounded visible Find outcomes, and the Basic Fertilizer consumable.
Purchase and Growth Charge replay ledgers, onboarding, loadout, entitlements,
and scheduler-day review state remain intact. Schema 20 is backed up before its
reward-state migration. Failed reads or writes remain fail-closed.

## Interface

- The Deck Browser, Overview, first-run state, active-plant state, and Settings adapt one shared preview snapshot. Its compact scenic postcard keeps weather, scenery, plants, foreground, and the watering can in one effects layer while the Garden name, plant summary, and **Open Garden** action remain legible.
- The Nursery and Collection cottage use artwork-following hover/focus outlines and in-scene labels. Nursery opens the catalog; the cottage opens Collection in the existing Garden Progress window. Both work with mouse and keyboard.
- The full Garden header gives the Garden name primary title position, followed by **Garden Progress**, **Collection**, and secondary **Settings** navigation.
- Long metric values keep their normal type size; the Nurtured Plant, Anki Streak, and Garden Coin groups wrap onto two rows when their measured content no longer fits.
- Watering cans use the six-bed geometry authority and row-level opaque planter-and-soil exclusions, so they stay beside the nurtured plant, clear of planter artwork, and behind the correct foreground layer in both Garden and Home renderers.
- Plant Story clearly separates editable plant name, species, stage, and Growth; it presents memories oldest to newest and a stage-relative **Up next** bar.
- Optional reviewer notices are quiet, silent, non-focus-stealing reward cards with relevant plant or item art.
- Collection is the collectible browser and Garden loadout manager. It derives categories from the registry, distinguishes explicit mysteries from ordinary locked items, manages plant placement, and owns reversible previews plus atomic equipment and visibility changes.
- Production Settings keeps only the applicable display/notification choices, uses automatically balanced artwork, and honors reduced motion automatically. Backup, populate, and restore controls exist only in an explicitly built capture package and are absent from the distributable.

## Runtime bundle

The distributable contains one current art line instead of retaining every
development generation:

- one canonical Verdant Twilight V6 responsive environment plus eight compatible Scenery reskins with unchanged masks, anchors, path, Nursery, and cottage;
- one approved transparent, pixel-lossless WebP for each of 10 species across 6 Growth stages;
- seven balanced transparent Weather overlays, three Growth Charge illustrations, and the lantern used at runtime.

V2–V5 scene and plant alternatives, migration-only catalogs, draft review
assets, and the packaged placeholder bitmap are excluded. Missing or unreadable
art does not alter saved plants or progression: the UI keeps the plant's name
and stage and draws its code-native fallback. The package tests enforce the
current-only file set and the release archive size ceiling for the complete
schema-21 scenery, plant, and planter library.

The accepted file count, byte size, and SHA-256 are recorded from the final
rebuilt archive only after the exact-package tests and complete UI capture pass.

## Troubleshooting

- **A plant is not receiving Growth:** open the Garden and make sure an unfinished plant is marked **Nurtured**. Reviews completed before choosing and nurturing a starter are intentionally not backfilled.
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
development-mutation capabilities off. A UI-capture package must be requested
explicitly and written to a different path:

```bash
./.venv/bin/python scripts/package_addon.py --capture \
  --output build/ui-face-captures/anki_garden_capture.ankiaddon
```

Capture builds cannot overwrite the production artifact.

## Development checks

```bash
./.venv/bin/pytest -q
PYTHONPYCACHEPREFIX=/private/tmp/anki-garden-pycache ./.venv/bin/python -m compileall -q ankigarden scripts tests
./.venv/bin/python scripts/audit_assets.py
./.venv/bin/python scripts/package_addon.py --production
python3 -m zipfile -t dist/anki_garden.ankiaddon
git diff --check
```

The runtime target is Anki 25.07 through 26.08. Release acceptance installs the exact rebuilt archive into a separately keyed, disposable Anki 26.08 base/profile with sync disabled.

The full product and QA contracts are in [`docs/feature-evidence-matrix.md`](docs/feature-evidence-matrix.md), [`docs/ui/data_contracts.md`](docs/ui/data_contracts.md), and [`docs/ui/state_scenarios.md`](docs/ui/state_scenarios.md).
