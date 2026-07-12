# Anki Garden 🌿

Anki Garden is a calm, local-first Anki add-on that turns everyday reviews into a growing hand-painted garden.

> Review cards → earn growth → complete gentle daily quests → unlock new garden expression.

## What it does

- Gives every answered card visible growth; difficult answers still contribute without removing progress.
- Tracks a daily goal, streak, garden vitality, quests, milestones, and plant stages.
- Adds a compact painted garden preview to Deck Browser and Overview with one clear Open Garden action.
- Provides a responsive garden dashboard with local storybook-gouache raster art plus scalable SVG UI and weather overlays.
- Saves garden appearance and motion preferences through Anki's configuration system.
- Stores progress only in `user_files/`, where Anki preserves it during add-on upgrades.

The focused 2.0 experience intentionally does not expose focus timers, exam mode, deck mapping, a shop, cloud/social features, or remote image downloads.

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
- `docs/storybook-gouache-assets.md`: production art direction, format policy, and v3 rollout rules.
- `docs/ui/`: UI state and data-contract references.

Garden progress is intentionally local. Deleting `ankigarden/user_files/garden_state.json` resets it.
