# Anki Garden 🌿

Anki Garden is a calm, local-first Anki add-on that turns card answers into a growing hand-painted garden.

> Card answers → Growth → plant stages
>
> Due-card completion, Anki streak milestones, and new plant stages → Garden Coins → Nursery plants, spaces, and Fertilizer

## Gameplay terms

| Term | What it means | Gameplay effect |
|---|---|---|
| **Card answer** | Choosing an answer button on a card that Anki Garden can count, including learning and relearning steps. | Gives the unfinished plant you nurture **10 base Growth**. |
| **Nurture** | Choose which unfinished plant receives future Growth. | Switching plants never moves Growth already earned. |
| **Growth** | A plant's progress toward its next visual stage. | Unlocks Seed, Sprout, Young, Mature, Flowering, and Rare stages. |
| **Anki streak** | Anki days in a row with at least one card answered. | Gives 0% Growth at day 1, then +5%, +10%, +15%, +20%, and +25% at days 7, 14, 30, 100, and 365. Milestones at 7, 14, 30, and 100 days also award Garden Coins. |
| **Garden Coins** | A separate spendable reward earned from study goals and milestones. | Buys Fertilizer, release-ready species, and garden spaces. It is never awarded for each card answer. |
| **Fertilizer** | A timed direct Growth boost for the plant you nurture. | Adds `+1`, `+2`, or `+3` Growth per answer while active. |

## Progression details

- Every eligible card answer gives the unfinished plant you nurture **10 base Growth** immediately.
- Growth is never split. Choosing **Nurture** changes which plant receives future Growth; it never moves Growth already earned.
- The current Anki streak adds a transparent Growth bonus: day 1 gives 0%; days 7, 14, 30, 100, and 365 unlock +5%, +10%, +15%, +20%, and +25% respectively. Missing an Anki day resets the next streak to day 1.
- Plants keep the existing Seed, Sprout, Young, Mature, Flowering, and Rare stages. The current thresholds are `0`, `500`, `2,500`, `8,000`, `20,000`, and `50,000` Growth.
- Stage-local feedback appears at 25%, 50%, 75%, and 100%. A plant that reaches Rare pauses; the learner chooses another unfinished plant to continue growing.

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
- Click selects one plant and opens a compact native card near it with stage-local Growth, answers remaining, Fertilizer status, and four stable actions: Nurture, Fertilize, Move, and Story.
- Click outside or press Escape to dismiss. The card repositions at scene edges and is replaced immediately when another plant is selected.
- Move highlights valid garden spaces. Click or keyboard-select one to save immediately, then use the inline Undo action if needed; Escape cancels before placement.
- Overlap hit testing follows depth order, and geometry-v2 `interaction_bounds` keep transparent artwork margins from stealing clicks.

The dashboard keeps only Plant Growth, Anki streak, and Garden Coins above the scene. Today, Achievements, and Collection live in the collapsed Progress drawer. Plant-specific information lives in the clicked-plant card or Plant Story.

Verdant Twilight V6 uses six direct-soil beds across three staggered perspective
bands. The nursery entrance is a keyboard-accessible landmark that opens the
Nursery from the full Garden, is disabled while moving a plant, and is not exposed
in the home preview. A fresh garden opens the Nursery on its first visit, offers
one release-ready starter for free, and begins with a second empty unlocked
space. Existing gardens preserve plant identity, names, Growth, stages, stories,
Fertilizer, ownership, and all other progression. An older scene layout refreshes
once: the nurtured unfinished plant is reseated and the others return safely to
Collection for placement in the rebuilt spaces.

## Fertilizer and collection

- Basic Fertilizer: 25 Garden Coins, `+1` Growth per answer, 1 hour.
- Quality Fertilizer: 65 Garden Coins, `+2` Growth per answer, 2 hours.
- Premium Fertilizer: 150 Garden Coins, `+3` Growth per answer, 4 hours.

Fertilizer adds direct Growth to the answer-time plant you nurture only while
its real elapsed-time activation interval is active. The choice card shows cost,
effect, and duration. Extending the same active tier keeps one continuous
interval. Replacing a different active tier requires confirmation and discards
its remaining time, but the completed portion is retained so a late same-day
sync still receives the tier active when answered. An expired interval is also
retained when Fertilizer is purchased again; answers before activation or at or
after expiry receive no Fertilizer Growth.

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
add-on upgrades. This pre-release redesign uses schema 14. Schema 10 is backed
up and converted to the current plant/stage contract; schemas 11, 12, and 13
migrate in place as established gardens. Entitlement-only species become usable
shelved plants. Migration waits for an authoritative scheduler-day read before
atomically converting the legacy scalar revlog cursor into the current-day ID
ledger, and backup/save failure leaves the original state untouched. Schema 14
records bounded per-plant Fertilizer activation history and a bounded
scheduler-day processed-ID ledger so late synced answers are counted exactly
once with the tier active at answer time and never receive a retroactive bonus.

## Interface

- The Deck Browser and Overview show a noninteractive garden preview, nurtured-plant Growth, Anki streak, Garden Coins, and one **Open Garden** action.
- The Nursery building is the only normal Nursery entry point. Its hover/focus glow and **Open Nursery** tooltip work with mouse and keyboard.
- Plant Story presents memories oldest to newest, an inline rename control, and an **Up next** milestone.
- Settings shows Verdant Twilight as the current read-only style, applies staged controls to a live preview, keeps advanced controls under **Fine tune**, and saves only through **Save settings**. Cancel discards staged changes; Troubleshooting remains separate.

## Runtime bundle

The distributable contains one current art line instead of retaining every
development generation:

- one Verdant Twilight V6 responsive environment;
- one approved transparent PNG for each of 10 species across 6 Growth stages;
- the weather overlays and lantern used at runtime under `assets/support/`.

V2–V5 scene and plant alternatives, migration-only catalogs, draft review
assets, and the packaged placeholder bitmap are excluded. Missing or unreadable
art does not alter saved plants or progression: the UI keeps the plant's name
and stage and draws its code-native fallback. The package tests enforce the
current-only file set and a 75 MiB archive ceiling.

## Install from source

Copy or symlink `ankigarden/` into Anki’s `addons21` directory, then restart Anki. Open the dashboard from **Tools → Anki Garden**.

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
