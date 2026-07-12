# Anki Garden 🌿

Anki Garden is a calm, local-first Anki add-on that turns everyday reviews into a growing hand-painted garden.

> Review cards → earn growth → complete gentle daily quests → unlock new garden expression.

## What it does

- Gives every answered card visible growth; the plant you nurture receives 80% while the rest share the remaining 20%.
- Tracks a daily goal, streak, garden vitality, quests, milestones, and plant stages.
- Adds a compact painted garden preview to Deck Browser and Overview with one clear Open Garden action.
- Provides a responsive garden dashboard with local storybook-gouache raster art, scalable SVG UI, weather overlays, and keyboard-friendly plant interactions.
- Lets you focus, nurture, move, swap, and undo plant arrangements while keeping growth totals consistent.
- Saves the daily goal, home visibility, garden appearance, and motion preferences through Anki's configuration system.
- Stores progress only in `user_files/`, where Anki preserves it during add-on upgrades.
- Offers a choice of new plants at calm review milestones instead of using a shop or spendable currency.
- Gives every plant a generated, editable name and a private milestone story built from growth, focus, streak, and review landmarks.

The focused 2.1 experience intentionally does not expose or persist focus timers, exam mode, deck mapping, a shop, currency/events/mastery systems, cloud/social features, or remote image downloads.

## What's new in 2.1

- Introduces the pre-release version 8 garden state; older development saves are backed up and reset before the first public release.
- Adds local plant stories with warm, factual milestone memories and inline renaming. No deck names or card content are stored.
- Repairs malformed plant IDs, slots, focus selection, and unlocked-space counts during load.
- Makes settings validation transactional so invalid values or a failed Anki config write cannot partially change the active experience.
- Hardens live and catch-up review processing so progress and its review cursor are saved together.
- Improves plant cards, placement controls, keyboard navigation, reduced-motion behavior, and narrow-window rendering.

The detailed release contract and validation scenarios are in [`docs/feature-evidence-matrix.md`](docs/feature-evidence-matrix.md).

## Install from source

Copy or symlink `ankigarden/` into Anki's `addons21` directory, then restart Anki. Open the dashboard from **Tools → Anki Garden**.

For a distributable package:

```bash
./.venv/bin/python scripts/package_addon.py
```

The artifact is written to `dist/anki_garden.ankiaddon`.

## Development checks

```bash
./.venv/bin/pytest -q
PYTHONPYCACHEPREFIX=/tmp/anki-garden-pycache python3 -m compileall -q ankigarden scripts tests
./.venv/bin/python scripts/audit_assets.py
./.venv/bin/python scripts/build_asset_gallery.py
./.venv/bin/python scripts/package_addon.py
python3 -m zipfile -t dist/anki_garden.ankiaddon
```

The current runtime target is Anki 25.07 through 26.5. Release acceptance uses the packaged artifact in a disposable Anki base/profile with sync disabled.

## Repository map

- `ankigarden/`: runtime, UI, state, configuration, and bundled artwork.
- `scripts/`: asset audit/gallery and package tooling.
- `tests/`: engine, state, UI-contract, integration, asset, and package checks.
- `docs/codebase-audit.md`: issue ledger and resolution evidence.
- `docs/feature-evidence-matrix.md`: automated and live-Anki release acceptance contract.
- `docs/storybook-gouache-assets.md`: production art direction, format policy, and v3 rollout rules.
- `docs/ui/`: UI state and data-contract references.

Garden progress is intentionally local. Deleting `ankigarden/user_files/garden_state.json` resets it.
