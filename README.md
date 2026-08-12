# Anki Garden 🌿

Anki Garden is a calm, local-first Anki add-on that turns card answers into a growing hand-painted garden.

> Card answers → Growth → plant stages
>
> Due-card completion, Anki streak milestones, plant stages, and rare study gifts → Garden Coins → Nursery plants, spaces, supplements, Weather, and Scenery

## Gameplay terms

| Term | What it means | Gameplay effect |
|---|---|---|
| **Card answer** | Choosing an answer button on a card that Anki Garden can count, including learning and relearning steps. | Gives the unfinished plant you nurture **10 base Growth**. |
| **Nurture** | Choose which unfinished plant receives future Growth. | Switching plants never moves Growth already earned. |
| **Growth** | A plant's progress toward its next visual stage. | Unlocks Seed, Sprout, Young, Mature, Flowering, and Rare stages. |
| **Anki streak** | Anki days in a row with at least one card answered. | Gives 0% Growth at day 1, then +5%, +10%, +15%, +20%, and +25% at days 7, 14, 30, 100, and 365. Milestones at 7, 14, 30, and 100 days also award Garden Coins. |
| **Garden Coins** | A separate spendable reward earned from study goals, milestones, and rare study gifts. | Buys Fertilizer, Growth Charges, release-ready species, garden spaces, Weather, and Scenery. |
| **Fertilizer** | A timed direct Growth boost for the plant you nurture. | Adds `+1`, `+2`, or `+3` Growth per answer while active. |
| **Booster Potion** | A rare, non-purchasable study gift kept in your collection. | Adds `+5` Growth per answer for two hours and stacks with Fertilizer. |
| **Growth Charge** | A stored one-use supplement applied to the unfinished plant you nurture. | Adds `+100`, `+500`, or `+2,000` Growth immediately, capped at Rare. |
| **Weather** | One equipped sky effect and its minor passive. | Can be shown or hidden without turning its passive off. |
| **Scenery** | One equipped reskin of the world around the fixed V6 garden. | Changes the setting and adds a passive without moving plants, Nursery, cottage, or path. |

## Progression details

- Every eligible card answer gives the unfinished plant you nurture **10 base Growth** immediately.
- Growth is never split. Choosing **Nurture** changes which plant receives future Growth; it never moves Growth already earned.
- The current Anki streak adds a transparent Growth bonus: day 1 gives 0%; days 7, 14, 30, 100, and 365 unlock +5%, +10%, +15%, +20%, and +25% respectively. Missing an Anki day resets the next streak to day 1.
- Plants keep the existing Seed, Sprout, Young, Mature, Flowering, and Rare stages. The current thresholds are `0`, `500`, `2,500`, `8,000`, `20,000`, and `50,000` Growth.
- Stage-local feedback appears at 25%, 50%, 75%, and 100%. A plant that reaches Rare pauses; the learner chooses another unfinished plant to continue growing.
- The current streak is reconstructed from Anki's review history at startup and after sync, so an existing consecutive run is reflected immediately. Previously reached streak Coin milestones are granted once.
- Each eligible, previously unseen answer runs one deterministic, ordered reward check. At most one reward band wins: Ultra Rare environment `1 in 100,000` before pity, Grand Charge `1 in 30,000`, Very Rare environment `1 in 20,000`, Standard Charge `1 in 8,000`, Rare environment `1 in 5,000`, Booster Potion `1 in 5,000`, Small Charge `1 in 2,000`, then 50 Garden Coins `1 in 800`. Historical reviews are never replayed for drops.

## Anki-day reward rules

An Anki day follows Anki's configured next-day cutoff. The first card answer on a new Anki day starts or continues the streak.

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
- Click selects one plant and opens a compact native card near it with stage-local Growth, answers remaining, Fertilizer and Booster status, and four stable actions: Nurture, Fertilize, Move, and Story.
- Click outside or press Escape to dismiss. The card repositions at scene edges and is replaced immediately when another plant is selected.
- Move highlights valid garden spaces. Click or keyboard-select one to save immediately, then use the inline Undo action if needed; Escape cancels before placement.
- Overlap hit testing follows depth order, and geometry-v2 `interaction_bounds` keep transparent artwork margins from stealing clicks.

The named Garden header, metric strip, and scene share one themed frame. Plant Growth, Anki streak, and Garden Coins are real buttons that open focused explanations with relative progress. **Progress** in the header—and the cottage inside the scene—opens the broader Today, Achievements, Collection, and progression guide window. Plant-specific information lives in the clicked-plant card or Plant Story.

Verdant Twilight V6 uses six direct-soil beds across three staggered perspective
bands. The nursery entrance is a keyboard-accessible landmark that opens the
Nursery from the full Garden, is disabled while moving a plant, and is not exposed
in the home preview. A fresh garden opens the Nursery on its first visit, offers
one release-ready starter for free, and begins with a second empty unlocked
space. The learner names the profile-wide Garden on first use and can rename it
later; new plants begin with an unambiguous generated name such as **Bonsai
Plant**. The Nursery is a warm catalog with **Plants**, **Supplements &
Boosters**, **Permanent Upgrades**, and **Weather & Scenery** tabs, stage
artwork previews, and item art.

## Fertilizer and collection

- Basic Fertilizer: 25 Garden Coins, `+1` Growth per answer, 1 hour.
- Quality Fertilizer: 65 Garden Coins, `+2` Growth per answer, 2 hours.
- Magical Fertilizer: 150 Garden Coins, `+3` Growth per answer, 4 hours.

Fertilizer adds direct Growth to the answer-time plant you nurture only while
its real elapsed-time activation interval is active. The choice card shows cost,
effect, and duration. Extending the same active tier keeps one continuous
interval. Replacing a different active tier requires confirmation and discards
its remaining time, but the completed portion is retained so a late same-day
sync still receives the tier active when answered. An expired interval is also
retained when Fertilizer is purchased again; answers before activation or at or
after expiry receive no Fertilizer Growth.

Booster Potions are not sold. A rare drop adds one to the collection; using it
on the nurtured unfinished plant grants `+5` Growth per eligible answer for two
hours. It stacks with Fertilizer, and using another Potion extends the active
Booster rather than discarding its remaining time.

Small and Standard Growth Charges can be bought repeatedly for 30 and 125
Garden Coins. They add 100 and 500 Growth immediately. The 2,000-Growth Grand
Charge is earn-only. Applying a Charge follows normal stage transitions and
stage Coin rewards, never grows beyond Rare, consumes nothing if saving fails,
and is tracked separately from answer-time Growth.

## Weather, Scenery, and rare rewards

Exactly one Weather and one Scenery may be equipped, and their passives stack.
The Nursery sells one-time Common and Uncommon choices but never auto-equips a
purchase. The cottage's **Weather & Scenery** collection tab shows the active
loadout, every effect, how each item is earned, exact drop odds, and Ultra pity.
Drop-only art remains a silhouette until unlocked while its rules stay visible.
Separate visibility switches hide either visual layer without disabling its
equipped passive.

Weather passives remain deliberately small: limited daily Growth, a small
all-due bonus, or a modest Booster-duration extension. Scenery can be stronger,
with the most powerful effects reserved for Very Rare and Ultra Rare review
drops. Daily scenery gifts require a card answer that Anki day, consume that
answer's one reward slot, and never backfill missed days. Ultra odds improve in
steps after 75,000 misses to a maximum `1 in 50,000`; there is no guaranteed
drop, and only an Ultra environment resets the pity counter. Completed Rare
environment tiers fall back to a Standard Charge; completed Very Rare or Ultra
tiers fall back to a Grand Charge.

The configured roster contains ten direct-soil species—Bonsai, Rose, Sunflower, Lavender, Hydrangea, Peony, Foxglove, Japanese Maple, Wisteria, and Dahlia—and up to six garden spaces. The Nursery lists a species only after its complete six-stage Verdant Twilight line is release-ready; all ten configured species are ready in the current bundle. Existing owned species remain usable even when they are not currently stocked. Shelving a plant preserves its Growth and story. Species cost 100–600 Garden Coins, and spaces three through six cost 150, 300, 500, and 800 Garden Coins.

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
add-on upgrades. The current pre-release state is schema 16. It stores Weather
and Scenery entitlements, loadout and visibility, Growth Charges, daily passive
claims, Ultra pity, separate Growth-source totals, the deterministic reward
seed/drop history, and the existing Garden, Booster, Fertilizer, and bounded
scheduler-day review state. Schema 15 development state is accepted and
upgraded; failed reads or writes remain fail-closed.

## Interface

- The Deck Browser and Overview use a compact, height-bounded, noninteractive scene preview with the Garden name, nurtured-plant Growth, Anki streak, Garden Coins, and one **Open Garden** action.
- The Nursery and cottage use artwork-following hover/focus outlines and in-scene labels. Nursery opens the catalog; the cottage opens Garden Progress. Both work with mouse and keyboard.
- Plant Story clearly separates editable plant name, species, stage, and Growth; it presents memories oldest to newest and a stage-relative **Up next** bar.
- Optional reviewer notices are quiet, silent, non-focus-stealing reward cards with relevant plant or item art.
- Weather and Scenery are equipped, changed, shown, and hidden from the cottage's collection window. They are no longer settings controls.
- Settings keeps only the applicable display/notification choices, uses automatically balanced artwork, and honors reduced motion automatically. The temporary Troubleshooting development controls can back up, populate, and restore a complete test garden.

## Runtime bundle

The distributable contains one current art line instead of retaining every
development generation:

- one canonical Verdant Twilight V6 responsive environment plus eight compatible Scenery reskins with unchanged masks, anchors, path, Nursery, and cottage;
- one approved transparent PNG for each of 10 species across 6 Growth stages;
- seven balanced transparent Weather overlays, three Growth Charge illustrations, and the lantern used at runtime.

V2–V5 scene and plant alternatives, migration-only catalogs, draft review
assets, and the packaged placeholder bitmap are excluded. Missing or unreadable
art does not alter saved plants or progression: the UI keeps the plant's name
and stage and draws its code-native fallback. The package tests enforce the
current-only file set and a 75 MiB archive ceiling.

## Install from source

Copy or symlink `ankigarden/` into Anki’s `addons21` directory, then restart Anki. Open the Garden from its Deck Browser or Overview card. Open settings from **Caleb M. Add-ons Settings → Anki Garden settings**.

Build the distributable package with:

```bash
./.venv/bin/python scripts/package_addon.py
```

The artifact is written to `dist/anki_garden.ankiaddon`.

## Development checks

```bash
./.venv/bin/pytest -q
PYTHONPYCACHEPREFIX=/private/tmp/anki-garden-pycache ./.venv/bin/python -m compileall -q ankigarden scripts tests
./.venv/bin/python scripts/audit_assets.py
./.venv/bin/python scripts/package_addon.py
python3 -m zipfile -t dist/anki_garden.ankiaddon
git diff --check
```

The runtime target is Anki 25.07 through 26.08. Release acceptance installs the exact rebuilt archive into a separately keyed, disposable Anki 26.08 base/profile with sync disabled.

The full product and QA contracts are in [`docs/feature-evidence-matrix.md`](docs/feature-evidence-matrix.md), [`docs/ui/data_contracts.md`](docs/ui/data_contracts.md), and [`docs/ui/state_scenarios.md`](docs/ui/state_scenarios.md).
