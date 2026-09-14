# Anki Garden

**Grow a garden while you study.**

Anki Garden is a free add-on for desktop Anki. Grow plants as you answer cards, collect new species, and customize your garden with scenery and decorations.

**Version 2.2.0** | [Watch the 26-second demo](release-copy/media/anki-garden-demo.mp4) | [Get started](#get-started) | [Progression and rewards](docs/progression-rewards-effects-reference.md) | [Report an issue](https://github.com/caleblee789/Anki-Gardening/issues)

This checkout is a release candidate. See the [release notes](docs/release-notes-2.2.0.md)
for its acceptance and publication status.

![Anki Garden promotional artwork with plants, garden beds, and decorations](docs/images/anki-garden-poster.png)

## Features

- **Grow your collection.** Choose from ten plant species, grow them from Seed to Full Bloom, and unlock more garden beds.
- **Make it yours.** Collect scenery and decorations, preview them in your garden, and equip your favorites.
- **Discover rewards.** Earn Coins and supplies, complete achievements, and unlock Gardening Trophies.
- **Follow your progress.** Keep the reviewer panel compact or expand it to see your plant, session totals, and recent rewards.

![Anki Garden reviewer showing the compact tile, expanded plant panel, and rewards](docs/images/anki-garden-review-hud.gif)

*This showcase demonstrates several reward states, not their typical frequency.*

## Get started

1. Install `anki_garden.ankiaddon` through **Tools → Add-ons → Install from file**, then restart Anki.
2. Select **Choose a plant** on Anki’s home screen. Your first plant is free.
3. Place it in a bed and select **Nurture** to choose which plant receives Growth.
4. Study as usual. Reopen the garden from the home screen or reviewer panel.

Use the packaged `.ankiaddon` file, not GitHub’s source-code ZIP.

## How it works

**Answer cards to earn Growth.** Again, Hard, Good, and Easy give the same base Growth, so choose the answer that reflects your recall. Plants grow through six stages:

Seed → Sprout → Young → Mature → Flowering → Full Bloom.

<table>
  <tr>
    <td align="center">
      <img src="output/promo/anki-garden-growth-showcase.gif" width="300" height="300" alt="Dahlia progressing from Seed through all six growth stages to Full Bloom">
      <br>
      <sub>Dahlia stage showcase.</sub>
    </td>
  </tr>
</table>

**Earn Coins and collect items.** Studying, milestones, and Garden Finds award in-game currency and rewards. Spend Coins in the Shop on plants, supplies, scenery, and decorations. Buying adds an item to your collection; equipping applies its artwork and effect. Previews are free and leave your saved equipment unchanged.

**Use supplies for a boost.** Fertilizer and Potions add bonus Growth for a set number of card answers. Growth Charges add a fixed amount immediately.

**Keep your earned streak bonuses.** Streak achievements unlock permanent Growth bonuses. Ending a streak does not remove your highest earned bonus.

See the [progression and rewards guide](docs/progression-rewards-effects-reference.md) for full rules, item effects, and unlock requirements.

## Find your way around

| Tab | What you can do |
| --- | --- |
| **Garden** | View, nurture, and move plants, or use supplies. |
| **Collection** | Browse plant stages and change scenery and decorations. |
| **Shop** | Buy plants, supplies, scenery, and decorations. |
| **Progress** | View activity, Study rewards, achievements, plant beds, and the Trophy Room. |

**Finish all cards due today** is the daily completion milestone in **Progress → Activity**. Session summaries show session earnings; your Coin balance shows what you have available to spend.

Garden settings let you adjust animations, reviewer panels, and reward summaries.

## Compatibility and limitations

**Release-candidate checks:** Anki 26.08.1 on macOS and Windows 11 ARM (native ARM and emulated x64), at 100% application scaling. Final release acceptance is pending. Physical Intel/AMD Windows hardware and Linux remain unverified.

The Garden interface runs only in desktop Anki, not AnkiMobile, AnkiDroid, or the AnkiWeb website. Inventory and settings are stored locally and do not sync between computers. Reviews from another device can earn rewards when their history syncs back to desktop Anki.

Compatibility with other add-ons may vary. See the [add-on interaction audit](docs/addon-compatibility-audit-20260908.md) for the scope and limits of existing checks.

**After Full Bloom**, extra Growth goes to other unfinished planted plants, then into Stored Growth. Stored Growth is saved but cannot be spent in this version.

## Help and feedback

[Open an issue](https://github.com/caleblee789/Anki-Gardening/issues) to report a bug or suggest an improvement. Include your Garden version, Anki version, operating system, and what happened versus what you expected.

For troubleshooting, use **Copy support report** in Garden settings. Review it before sharing. Screenshots and error messages are helpful, but remove private information first. Do not upload collections, private card content, patient information, or personal file paths.

## Development and maintenance

Developed and maintained by **Caleb Meadows** ([caleblee789](https://github.com/caleblee789)), a medical student and Anki add-on maintainer. Caleb oversees development, reviews changes, validates releases, and handles compatibility, documentation, and user reports.

See the [development guide](docs/development.md) for setup and contribution details.

## License and acknowledgments

**Code:** [AGPL-3.0-or-later](LICENSE).

**Project artwork:** [CC BY 4.0](LICENSES/CC-BY-4.0.txt), to the extent of rights held by the project. Artwork includes AI-generated assets. Third-party material retains its original terms. See [licensing and credits](LICENSING.md) for attribution, scope, and exceptions.

Anki Garden is an independent add-on, not an official Anki product.
